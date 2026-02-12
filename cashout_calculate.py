def calculate_cashout(player_sum, dealer_card, is_soft=False):
    """
    計算 Blackjack 預期兌現金額
    
    參數:
    player_sum (int): 玩家點數總和 (例如: 16)
    dealer_card (int): 莊家明牌點數 (A=11, J/Q/K=10)
    is_soft (bool): 是否為軟牌 (手牌含 Ace 且算 11 點不爆牌，例如 A+5=16)
    
    返回:
    int: 預估兌現金額
    """
    
    P = player_sum
    D = dealer_card
    
    # 參數驗證
    if not (4 <= P <= 21):
        return 0  # 點數不合理
    if not (2 <= D <= 11):
        return 0  # 莊家牌不合理

    if not is_soft:
        # --- 硬牌公式 (Hard Hand) ---
        # 基於三次多項式回歸 (R^2 ≈ 0.83)
        cashout = (
            -475.55 
            + 147.51 * P 
            + 43.17 * D 
            - 13.06 * P**2 
            - 0.26 * P * D 
            - 6.97 * D**2 
            + 0.36 * P**3 
            + 0.007 * P**2 * D 
            + 0.015 * P * D**2 
            + 0.30 * D**3
        )
    else:
        # --- 軟牌公式 (Soft Hand) ---
        # 基於三次多項式回歸 (R^2 ≈ 0.92)
        cashout = (
            607.53 
            - 76.03 * P 
            + 75.39 * D 
            + 2.48 * P**2 
            - 4.52 * P * D 
            - 5.30 * D**2 
            + 0.007 * P**3 
            + 0.075 * P**2 * D 
            + 0.176 * P * D**2 
            + 0.039 * D**3
        )
        
    # 確保金額不為負數，並四捨五入取整
    return max(0, int(round(cashout)))

# --- 測試範例 (您可以修改這裡的數值) ---
if __name__ == "__main__":
    test_cases = [
        # (玩家點數, 莊家明牌, 是否軟牌, 預期結果)
        (20, 10, False, "硬 20 vs 10 (強牌)"),
        (16, 10, False, "硬 16 vs 10 (弱牌)"),
        (16, 6,  False, "硬 16 vs 6  (賭莊家爆)"),
        (16, 6,  True,  "軟 16 vs 6  (軟牌優勢)"), 
        (11, 10, False, "硬 11 vs 10 (加倍機會)"),
        (12, 6,  True,  "軟 12 (AA) vs 6 (極強起手)"),
    ]

    print(f"{'玩家':<6} {'莊家':<6} {'類型':<6} {'預測兌現':<10} {'說明'}")
    print("-" * 50)
    
    for p, d, s, desc in test_cases:
        amt = calculate_cashout(p, d, s)
        type_str = "軟牌" if s else "硬牌"
        print(f"{p:<8} {d:<8} {type_str:<8} {amt:<12} {desc}")