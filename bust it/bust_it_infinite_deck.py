import random
import time

def simulate_infinite_deck_bust_it(num_simulations=50000000):
    print(f"--- 啟動終極驗證：無限副牌模型 (Infinite Deck) ---")
    print(f"假設：官方 94.12% 是基於無限牌組計算的")
    print(f"模擬手數: {num_simulations} (50M) | 規則: S17")
    
    start_time = time.time()
    
    # 賠率表
    payouts = {3: 1, 4: 2, 5: 9, 6: 50, 7: 100, 8: 250}
    
    total_return = 0
    bust_counts = {k: 0 for k in range(3, 10)}
    
    # 無限副牌模型：
    # 不需要建立 massive shoe，只需要定義單副牌的結構
    # 每次抽牌都視為獨立事件 (With Replacement)
    single_deck_cards = [2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11] * 4
    
    # 優化：直接使用 random.choices (有放回抽樣)
    # 這比 random.sample (無放回) 快且符合無限牌定義
    choices_func = random.choices
    
    # 為了進度顯示
    chunk_size = 1000000 
    
    for i in range(num_simulations // chunk_size):
        # 顯示進度
        if i % 5 == 0 and i > 0:
             current_rtp = (total_return / (i * chunk_size)) * 100
             print(f"進度: {i}M / {num_simulations//1000000}M | 當前 RTP: {current_rtp:.4f}%")

        for _ in range(chunk_size):
            # 核心差異：choices (無限牌)
            cards = choices_func(single_deck_cards, k=12)
            
            hand_value = 0
            card_count = 0
            aces = 0
            idx = 0
            
            # S17 邏輯
            while hand_value < 17:
                card = cards[idx]
                idx += 1
                card_count += 1
                hand_value += card
                if card == 11:
                    aces += 1
                while hand_value > 21 and aces > 0:
                    hand_value -= 10
                    aces -= 1
            
            if hand_value > 21:
                final_count = card_count if card_count < 8 else 8
                bust_counts[final_count] += 1
                total_return += (1 + payouts[final_count])

    final_rtp = (total_return / num_simulations) * 100
    
    print("\n" + "="*50)
    print(f"無限副牌模擬結束")
    print(f"最終 RTP: {final_rtp:.5f}%")
    print(f"官方 RTP: 94.12%")
    print(f"誤差: {final_rtp - 94.12:.5f}%")
    print("="*50)
    
    # 輸出機率分佈以供理論對照
    print("詳細機率分佈 (Infinite Deck Probabilities):")
    for c in range(3, 9):
        label = f"{c} 張" if c < 8 else "8+ 張"
        prob = (bust_counts[c] / num_simulations)
        print(f"  {label}: {prob:.6f}")

if __name__ == "__main__":
    # 跑 5000 萬次，這會給出非常穩定的無限牌數值
    simulate_infinite_deck_bust_it(1000000000)