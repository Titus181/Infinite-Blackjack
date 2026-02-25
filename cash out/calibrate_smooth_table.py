# -*- coding: utf-8 -*-
"""
校準平滑推算表：僅調整「原始數據表中為 - 的格子」，其餘格子完全不動。
對「-」格加上常數 δ（優化 δ 使 RTP 逼近 96.80%），公式：新值 = 原值 + δ，限制在 [50, 200]。
僅改動「-」格，不做整張表縮放。
"""
import os
import sys
import pandas as pd
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
ORIGINAL_PATH = os.path.join(DATA_DIR, "blackjack 對照表 - 原始數據整理表.csv")
SMOOTH_PATH = os.path.join(DATA_DIR, "blackjack 對照表 - 平滑推算表.csv")
TARGET_RTP = 96.80

# 優化時模擬局數（較小以加速），正式驗證可用 1e7；可設環境變數 CALIBRATION_ROUNDS 覆寫
CALIBRATION_ROUNDS = int(os.environ.get("CALIBRATION_ROUNDS", "500000"))


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


def load_original_and_mask():
    """
    載入原始數據表，回傳三個區塊的「-」遮罩（True 表示該格原始為缺漏）。
    遮罩的欄位已正規化為 2..11，與平滑表一致。
    """
    df_hard = pd.read_csv(ORIGINAL_PATH, skiprows=1, nrows=15, index_col=0)
    df_soft = pd.read_csv(ORIGINAL_PATH, skiprows=19, nrows=9, index_col=0)
    df_split = pd.read_csv(ORIGINAL_PATH, skiprows=32, nrows=12, index_col=0)

    def is_missing(val):
        if pd.isna(val):
            return True
        s = str(val).strip()
        return s == "-" or s == ""

    def build_mask(df):
        try:
            mask = df.map(is_missing)
        except AttributeError:
            mask = df.applymap(is_missing)
        mask = _normalize_columns(mask)
        return mask

    return {
        "hard": build_mask(df_hard),
        "soft": build_mask(df_soft),
        "split": build_mask(df_split),
    }


def load_smooth_tables():
    """載入當前平滑推算表（三個區塊）。"""
    df_hard = pd.read_csv(SMOOTH_PATH, skiprows=1, nrows=15, index_col=0)
    df_soft = pd.read_csv(SMOOTH_PATH, skiprows=19, nrows=9, index_col=0)
    df_split = pd.read_csv(SMOOTH_PATH, skiprows=32, nrows=12, index_col=0)

    df_hard = _normalize_columns(df_hard)
    df_soft = _normalize_columns(df_soft)
    df_split = _normalize_columns(df_split)
    return {"hard": df_hard, "soft": df_soft, "split": df_split}


def apply_delta_to_filled_cells(smooth_tables, masks, delta):
    """
    複製平滑表，僅對「原始為 -」的格子加上常數 delta，其餘不變。
    新值 = 原值 + delta，限制在 [50, 200]。只改「-」格。
    """
    out = {}
    for block in ("hard", "soft", "split"):
        df = smooth_tables[block].copy()
        mask = masks[block]
        for idx in df.index:
            for col in df.columns:
                try:
                    if idx not in mask.index or col not in mask.columns:
                        continue
                    if not mask.loc[idx, col]:
                        continue
                    old = float(df.loc[idx, col])
                    new = old + delta
                    df.loc[idx, col] = max(50.0, min(200.0, new))
                except (TypeError, ValueError, KeyError):
                    pass
        out[block] = df
    return out


def _get_rtp_module():
    """載入 RTP 模組。"""
    from importlib.util import spec_from_file_location, module_from_spec
    spec = spec_from_file_location("rtp", os.path.join(SCRIPT_DIR, "cash out RTP.py"))
    rtp_module = module_from_spec(spec)
    spec.loader.exec_module(rtp_module)
    return rtp_module


def run_simulation_with_tables(tables, n_rounds):
    """呼叫 RTP 模組的 run_simulation。"""
    rtp_module = _get_rtp_module()
    _, _, rtp_pct = rtp_module.run_simulation(tables, int(n_rounds), seed=42)
    return rtp_pct


def run_simulation_estimate_filled(tables, masks, n_rounds, seed=42):
    """
    跑一次模擬，回傳 (當前 RTP%, 兌現時命中「-」格的機率 p_filled)。
    用於直接計算 δ = (TARGET_RTP - 當前RTP) / p_filled。
    """
    import random
    rtp_module = _get_rtp_module()
    random.seed(seed)
    shoe = rtp_module.create_shoe(8)
    total_returned = 0.0
    n_filled = 0
    n_rounds = int(n_rounds)
    for _ in range(n_rounds):
        amt, key = rtp_module.play_round(shoe, tables)
        total_returned += amt
        if key is not None:
            block, row, col = key
            try:
                if block in masks and row in masks[block].index and col in masks[block].columns:
                    if masks[block].loc[row, col]:
                        n_filled += 1
            except (KeyError, TypeError):
                pass
    total_bet = n_rounds * rtp_module.BASE_BET
    rtp_pct = (total_returned / total_bet) * 100
    p_filled = n_filled / n_rounds if n_rounds else 0.0
    return rtp_pct, p_filled


def objective_delta(delta, smooth_tables, masks):
    """目標：| RTP - TARGET_RTP | 最小（僅對「-」格加 delta）。"""
    tables = apply_delta_to_filled_cells(smooth_tables, masks, delta)
    rtp = run_simulation_with_tables(tables, CALIBRATION_ROUNDS)
    return abs(rtp - TARGET_RTP)


def main():
    print("載入原始數據表與「-」遮罩...")
    masks = load_original_and_mask()
    n_filled = sum(int(masks[b].sum().sum()) for b in ("hard", "soft", "split"))
    print(f"  原始表中為「-」的格子數: {n_filled}")

    print("載入平滑推算表...")
    smooth_tables = load_smooth_tables()

    print(f"目標 RTP: {TARGET_RTP}%")
    print(f"校準模擬局數: {CALIBRATION_ROUNDS} (用於估計當前 RTP 與「-」格出現率)")
    print("估計當前 RTP 與兌現時命中「-」格的機率...")
    current_rtp, p_filled = run_simulation_estimate_filled(smooth_tables, masks, CALIBRATION_ROUNDS)
    print(f"  當前 RTP: {current_rtp:.2f}%")
    print(f"  兌現時命中「-」格機率: {p_filled:.2%}")

    if p_filled < 0.005:
        print("  警告：命中「-」格機率過低，無法單靠調整「-」格達到目標 RTP。")
        delta_opt = 0.0
    else:
        # 直接公式：每局平均需多拿 (TARGET_RTP - current_rtp)，每命中「-」格一次多拿 δ → δ = (TARGET_RTP - current_rtp) / p_filled
        delta_opt = (TARGET_RTP - current_rtp) / p_filled
        delta_opt = max(0.0, min(80.0, delta_opt))
        print(f"  依公式計算 δ = (目標 - 當前) / p_filled ≈ {delta_opt:.1f}")

    tables_calibrated = apply_delta_to_filled_cells(smooth_tables, masks, delta_opt)
    rtp_cal = run_simulation_with_tables(tables_calibrated, CALIBRATION_ROUNDS)
    print(f"  僅調整「-」格後 RTP (約 {CALIBRATION_ROUNDS} 局): {rtp_cal:.2f}%")

    # 寫出新的平滑推算表（僅「-」格被加上 δ，其餘與原平滑表相同）
    out_path = SMOOTH_PATH
    backup_path = os.path.join(DATA_DIR, "blackjack 對照表 - 平滑推算表.backup.csv")
    if os.path.exists(out_path):
        import shutil
        shutil.copy(out_path, backup_path)
        print(f"  已備份原表至: {backup_path}")

    def _write_block(f, title, df):
        f.write(title + "\n")
        header = "您的點數 \\ 莊家," + ",".join(
            "A (11)" if c == 11 else str(c) for c in df.columns
        ) + "\n"
        f.write(header)
        for idx in df.index:
            row_vals = [
                str(int(round(float(df.loc[idx, c])))) if pd.notna(df.loc[idx, c]) else ""
                for c in df.columns
            ]
            # 列名含逗號（如 "20 (A,9)"）必須用雙引號包住，否則 CSV 解析會錯
            idx_str = str(idx)
            if "," in idx_str:
                idx_str = '"' + idx_str + '"'
            f.write(idx_str + "," + ",".join(row_vals) + "\n")

    with open(out_path, "w", encoding="utf-8") as f:
        _write_block(f, "硬牌,,,,,,,,,,", tables_calibrated["hard"])
        f.write(",,,,,,,,,,\n")
        _write_block(f, "軟牌,,,,,,,,,,", tables_calibrated["soft"])
        f.write(",,,,,,,,,,\n")
        f.write(",,,,,,,,,,\n")
        _write_block(f, "分牌,,,,,,,,,,", tables_calibrated["split"])

    print(f"已寫入校準後平滑推算表: {out_path}")
    print("請再執行「cash out RTP.py」用 1000 萬局驗證 RTP。")


if __name__ == "__main__":
    main()
