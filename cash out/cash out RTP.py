import pandas as pd
import random
import numpy as np
import os

# --- 1. 遊戲基本設定 ---
BASE_BET = 100
SIMULATION_ROUNDS = 100000000  # 模擬局數，可依需求調高以增加精準度

# 是否一併計算「平滑推算表.backup.csv」的 RTP（True=兩張表各算策略 A/B；False=僅算平滑推算表.csv）
CALCULATE_BACKUP_RTP = False

# 以腳本所在目錄為基準，確保無論從哪裡執行都能找到 data
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(SCRIPT_DIR, "data", "blackjack 對照表 - 平滑推算表.csv")
DATA_PATH_BACKUP = os.path.join(SCRIPT_DIR, "data", "blackjack 對照表 - 平滑推算表.backup.csv")
ORIGINAL_DATA_PATH = os.path.join(SCRIPT_DIR, "data", "blackjack 對照表 - 原始數據整理表.csv")

# 莊家明牌欄位對應 (CSV 欄位名 -> 整數)
DEALER_COLS = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11]  # A = 11

def create_shoe(num_decks=8):
    """建立 8 副牌的牌靴"""
    # 牌值：2-10 直接對應，J, Q, K 當作 10，A 當作 11
    single_deck = [2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11] * 4
    shoe = single_deck * num_decks
    random.shuffle(shoe)
    return shoe

def calculate_hand(cards):
    """
    計算手牌點數
    回傳: (總點數, 是否為軟牌)
    """
    total = sum(cards)
    aces = cards.count(11)
    
    # 處理 A 的點數 (11 或 1)
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
        
    is_soft = aces > 0 and total <= 21
    return total, is_soft

def dealer_play(shoe, dealer_cards):
    """莊家補牌邏輯：Infinite Blackjack 莊家通常在軟 17 停牌 (Stands on Soft 17)"""
    while True:
        total, is_soft = calculate_hand(dealer_cards)
        if total < 17:
            dealer_cards.append(shoe.pop())
        else:
            break
    return total

def load_cashout_tables(csv_path):
    """
    從 CSV 載入三個區塊：硬牌、軟牌、分牌。
    回傳 dict: {'hard': df, 'soft': df, 'split': df}，欄位已正規化為 2..10, 11(A)。
    """
    def _normalize_columns(df):
        cols = []
        for c in df.columns:
            s = str(c).replace("A (11)", "11").replace("A", "11").strip()
            try:
                cols.append(int(s))
            except ValueError:
                cols.append(c)
        df = df.copy()
        df.columns = cols
        return df

    # CSV 結構：硬牌區 第1行標題、第2行起為 header、之後 15 行資料；軟牌區 第19行 header、9 行資料；分牌區 第32行 header、12 行資料
    df_hard = pd.read_csv(csv_path, skiprows=1, nrows=15, index_col=0)
    df_soft = pd.read_csv(csv_path, skiprows=19, nrows=9, index_col=0)
    df_split = pd.read_csv(csv_path, skiprows=32, nrows=12, index_col=0)

    df_hard = _normalize_columns(df_hard)
    df_soft = _normalize_columns(df_soft)
    df_split = _normalize_columns(df_split)
    return {"hard": df_hard, "soft": df_soft, "split": df_split}


def _soft_row_name(player_total):
    """軟牌點數對應 CSV 列名：20 -> '20 (A,9)', 12 -> '12 (A,A)' 等。"""
    if player_total == 12:
        return "12 (A,A)"
    if 13 <= player_total <= 20:
        return f"{player_total} (A,{player_total - 11})"
    return None


def get_cashout_value(tables, player_total, dealer_upcard, is_soft, is_pair, base_bet):
    """
    從兌現表中查找金額，依牌型使用硬牌 / 軟牌 / 分牌區塊。
    tables: dict from load_cashout_tables()。
    若有對應不到則回傳保守估計 (注金 80%)。
    """
    col = int(dealer_upcard) if dealer_upcard != 11 else 11
    if col == 1:
        col = 11
    try:
        if is_pair:
            df = tables["split"]
            row = player_total
        elif is_soft:
            df = tables["soft"]
            row = _soft_row_name(player_total)
            if row is None or row not in df.index:
                return base_bet * 0.8
        else:
            df = tables["hard"]
            row = player_total

        if row not in df.index or col not in df.columns:
            return base_bet * 0.8
        cashout = float(df.loc[row, col])
        return cashout * (base_bet / 100.0)
    except (KeyError, TypeError):
        return base_bet * 0.8


def _resolve_single_hand(shoe, cards, dealer_upcard, tables, base_bet):
    """
    單手「可兌換就兌現、否則比牌」。供策略 B 分牌後每手使用。
    分牌後再成對視為 is_pair=True 可兌現、不允許再分。
    回傳該手拿回金額。
    """
    total, is_soft = calculate_hand(cards)
    if total > 21:
        return 0.0
    is_pair = len(cards) == 2 and cards[0] == cards[1]
    can_cash = is_pair or is_soft or total < 17
    if can_cash:
        return get_cashout_value(tables, total, dealer_upcard, is_soft, is_pair, base_bet)
    # 硬 17+：莊家補牌並比大小
    dealer_cards = [dealer_upcard, shoe.pop()]
    dealer_final = dealer_play(shoe, dealer_cards)
    if dealer_final > 21:
        return base_bet * 2
    if total > dealer_final:
        return base_bet * 2
    if total == dealer_final:
        return base_bet
    return 0.0


def play_round(shoe, df_table):
    """模擬單局遊戲（策略 A：第一次可兌換就兌換，對子不分牌直接兌現）。回傳 (amount, key)。"""
    # 若牌靴剩餘牌量不足，重新洗牌 (設定為低於 1 Deck 時洗牌)
    if len(shoe) < 52:
        shoe.extend(create_shoe(8))
        random.shuffle(shoe)

    # 初始發牌
    player_cards = [shoe.pop(), shoe.pop()]
    dealer_cards = [shoe.pop()]  # 莊家明牌
    # 莊家暗牌先扣著，這裡為了簡化我們先不抽出暗牌，等輪到莊家再抽即可
    
    dealer_upcard = dealer_cards[0]

    # --- 檢查玩家是否有 Blackjack ---
    player_total, is_soft = calculate_hand(player_cards)
    if player_total == 21 and len(player_cards) == 2:
        # 玩家 BJ，莊家需要檢查是否也 BJ
        dealer_hidden = shoe.pop()
        dealer_cards.append(dealer_hidden)
        dealer_total, _ = calculate_hand(dealer_cards)
        
        if dealer_total == 21:
            return BASE_BET, None  # Push (退回本金 100)
        else:
            return BASE_BET * 2.5, None  # BJ 賠 3:2，含本金拿回 250

    # --- 判斷是否觸發「兌現 (Cash Out)」 ---
    # 根據規則：硬 17 以上 (且非對子) 無法補牌/分牌 -> 直接停牌
    # 其餘情況 (硬 < 17、軟牌、對子) -> 觸發兌現
    is_pair = (len(player_cards) == 2 and player_cards[0] == player_cards[1])
    can_cash_out = False
    
    if is_pair:
        can_cash_out = True
    elif is_soft:
        can_cash_out = True
    elif player_total < 17:
        can_cash_out = True

    # --- 策略：始終兌現 (Always Cash Out) ---
    if can_cash_out:
        # 直接拿兌現金額走人（依硬牌/軟牌/分牌選對應區塊）
        cashout_amount = get_cashout_value(
            df_table, player_total, dealer_upcard, is_soft, is_pair, BASE_BET
        )
        # 供校準腳本：回傳兌現時查表的 (區塊, 列, 欄)
        col = 11 if dealer_upcard == 11 else int(dealer_upcard)
        if is_pair:
            cashout_key = ("split", player_total, col)
        elif is_soft:
            cashout_key = ("soft", _soft_row_name(player_total), col)
        else:
            cashout_key = ("hard", player_total, col)
        return cashout_amount, cashout_key
    else:
        # --- 硬 17 以上，系統不給兌現，強制停牌，與莊家比大小 ---
        dealer_cards.append(shoe.pop())
        dealer_final = dealer_play(shoe, dealer_cards)
        if dealer_final > 21:
            return BASE_BET * 2, None
        elif player_total > dealer_final:
            return BASE_BET * 2, None
        elif player_total == dealer_final:
            return BASE_BET, None
        else:
            return 0, None


def _play_round_strategy_b(shoe, tables):
    """
    策略 B 單局：若初始為對子則分牌，兩手各補一張後每手可兌換就兌現、否則比牌。
    回傳 (amount, bet_amount)，bet_amount 為 1 或 2 注。
    """
    if len(shoe) < 52:
        shoe.extend(create_shoe(8))
        random.shuffle(shoe)

    player_cards = [shoe.pop(), shoe.pop()]
    dealer_cards = [shoe.pop()]
    dealer_upcard = dealer_cards[0]

    player_total, is_soft = calculate_hand(player_cards)
    if player_total == 21 and len(player_cards) == 2:
        dealer_hidden = shoe.pop()
        dealer_cards.append(dealer_hidden)
        dealer_total, _ = calculate_hand(dealer_cards)
        if dealer_total == 21:
            return BASE_BET, BASE_BET
        return BASE_BET * 2.5, BASE_BET

    is_pair = player_cards[0] == player_cards[1]
    if not is_pair:
        amount = _resolve_single_hand(shoe, player_cards, dealer_upcard, tables, BASE_BET)
        return amount, BASE_BET

    # 分牌：兩手各補一張
    c1, c2 = player_cards[0], player_cards[1]
    hand1 = [c1, shoe.pop()]
    hand2 = [c2, shoe.pop()]
    r1 = _resolve_single_hand(shoe, hand1, dealer_upcard, tables, BASE_BET)
    r2 = _resolve_single_hand(shoe, hand2, dealer_upcard, tables, BASE_BET)
    return r1 + r2, 2 * BASE_BET


def run_simulation(tables, n_rounds, seed=None, strategy='A'):
    """
    使用給定的兌現表執行 n_rounds 局，回傳 (總拿回金額, 總下注金額, RTP%)。
    供校準腳本呼叫，可傳入修改後的 tables。
    strategy: 'A' 第一次可兌換就兌換、對子不分牌；'B' 對子分牌後兩手各自兌現。
    """
    if seed is not None:
        random.seed(seed)
    shoe = create_shoe(8)
    total_returned = 0.0
    total_bet = 0.0
    if strategy == 'A':
        for _ in range(n_rounds):
            amt, _ = play_round(shoe, tables)
            total_returned += amt
        total_bet = n_rounds * BASE_BET
    else:
        for _ in range(n_rounds):
            amt, bet_amt = _play_round_strategy_b(shoe, tables)
            total_returned += amt
            total_bet += bet_amt
    rtp_pct = (total_returned / total_bet) * 100 if total_bet > 0 else 0.0
    return total_returned, total_bet, rtp_pct


def run_rtp_for_table(tables, table_label, n_rounds):
    """
    對單一兌現表依序跑策略 A、策略 B，並印出該表名稱下的兩組 RTP 結果。
    回傳 (rtp_a, rtp_b) 方便彙總顯示。
    """
    shoe = create_shoe(8)

    # --- 策略 A ---
    print(f"\n開始模擬 [{table_label}] 策略 A...")
    total_returned_a = 0.0
    for i in range(n_rounds):
        amt, _ = play_round(shoe, tables)
        total_returned_a += amt
        if (i + 1) % 1000000 == 0:
            current_rtp = (total_returned_a / ((i + 1) * BASE_BET)) * 100
            print(f"  已模擬 {i + 1} 局 | 目前估計 RTP: {current_rtp:.2f}%")
    total_bet_a = n_rounds * BASE_BET
    rtp_a = (total_returned_a / total_bet_a) * 100
    print(f"\n=== {table_label} - 策略 A 最終結果 ===")
    print(f"總模擬局數: {n_rounds}")
    print(f"總下注金額: {total_bet_a}")
    print(f"總拿回金額: {total_returned_a:.2f}")
    print(f"★ 策略 A RTP: {rtp_a:.2f}%")

    # --- 策略 B ---
    print(f"\n開始模擬 [{table_label}] 策略 B...")
    shoe = create_shoe(8)
    total_returned_b = 0.0
    total_bet_b = 0.0
    for i in range(n_rounds):
        amt, bet_amt = _play_round_strategy_b(shoe, tables)
        total_returned_b += amt
        total_bet_b += bet_amt
        if (i + 1) % 1000000 == 0:
            current_rtp = (total_returned_b / total_bet_b) * 100
            print(f"  已模擬 {i + 1} 局 | 目前估計 RTP: {current_rtp:.2f}%")
    rtp_b = (total_returned_b / total_bet_b) * 100 if total_bet_b > 0 else 0.0
    print(f"\n=== {table_label} - 策略 B 最終結果 ===")
    print(f"總模擬局數: {n_rounds}")
    print(f"總下注金額: {total_bet_b}")
    print(f"總拿回金額: {total_returned_b:.2f}")
    print(f"★ 策略 B RTP: {rtp_b:.2f}%")
    return rtp_a, rtp_b


# --- 主程式 ---
def main():
    print("正在載入兌現對照表...")
    n_rounds = SIMULATION_ROUNDS

    rtp_summary = []

    try:
        tables_smooth = load_cashout_tables(DATA_PATH)
    except Exception as e:
        print(f"讀取平滑推算表 CSV 失敗: {e}")
        return

    rtp_a_smooth, rtp_b_smooth = run_rtp_for_table(tables_smooth, "平滑推算表", n_rounds)
    rtp_summary.append(("平滑推算表", rtp_a_smooth, rtp_b_smooth))

    if CALCULATE_BACKUP_RTP:
        try:
            tables_backup = load_cashout_tables(DATA_PATH_BACKUP)
        except Exception as e:
            print(f"\n讀取平滑推算表.backup CSV 失敗: {e}，跳過 backup 的兩組 RTP")
        else:
            rtp_a_backup, rtp_b_backup = run_rtp_for_table(tables_backup, "平滑推算表.backup", n_rounds)
            rtp_summary.append(("平滑推算表.backup", rtp_a_backup, rtp_b_backup))

    if rtp_summary:
        print("\n=== RTP 總覽 ===")
        print("對照表\t\t策略 A RTP\t策略 B RTP")
        for label, rtp_a, rtp_b in rtp_summary:
            print(f"{label}\t{rtp_a:.2f}%\t\t{rtp_b:.2f}%")

if __name__ == "__main__":
    main()