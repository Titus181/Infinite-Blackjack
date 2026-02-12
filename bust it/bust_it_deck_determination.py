import random
import time

def find_evolution_magic_number_precision(simulation_hands=20000000):
    print(f"--- 啟動 Evolution 逆向工程 (高精度狙擊模式) ---")
    print(f"目標 RTP: 94.12% | 規則: S17 | 每組手數: {simulation_hands} (20M)")
    print(f"說明：大幅增加手數以消除 250倍 大獎帶來的統計波動\n")
    
    # 我們鎖定 12 ~ 20 副牌這個區間進行地毯式搜索
    deck_counts_to_test = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25]
    
    payouts = {3: 1, 4: 2, 5: 9, 6: 50, 7: 100, 8: 250}
    
    results = {}

    for num_decks in deck_counts_to_test:
        print(f"正在測試 {num_decks} 副牌... ", end="", flush=True)
        
        # 建立牌庫
        single_deck = [2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11] * 4
        full_shoe = single_deck * num_decks
        
        total_return = 0
        
        # 優化：提取 random.sample
        sample_func = random.sample
        
        start_t = time.time()
        
        # 為了進度顯示，分塊執行
        chunk_size = 1000000 # 每次跑 100 萬更新一次狀態(不顯示但在變數裡)
        
        for _ in range(simulation_hands // chunk_size):
            # 小迴圈
            for _ in range(chunk_size):
                cards = sample_func(full_shoe, 12)
                
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
                    total_return += (1 + payouts[final_count])
        
        elapsed = time.time() - start_t
        rtp = (total_return / simulation_hands) * 100
        results[num_decks] = rtp
        
        # 計算與官方的差距
        diff = rtp - 94.12
        sign = "+" if diff > 0 else ""
        print(f"完成! RTP: {rtp:.5f}% | 誤差: {sign}{diff:.4f}% | 耗時: {elapsed:.1f}s")

    print("\n" + "="*50)
    print("高精度總結分析:")
    print("="*50)
    
    best_deck = None
    min_diff = 100
    
    for d, r in results.items():
        diff = abs(r - 94.12)
        if diff < min_diff:
            min_diff = diff
            best_deck = d
        print(f"{d:2d} Decks -> RTP: {r:.5f}%")
        
    print("-" * 50)
    print(f"最接近官方 94.12% 的模型是: {best_deck} 副牌")
    print(f"(這代表 Evo 的數學模型將 '洗牌機延遲' 等效為了 {best_deck} 副牌的厚度)")

if __name__ == "__main__":
    find_evolution_magic_number_precision(20000000)