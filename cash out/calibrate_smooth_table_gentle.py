# -*- coding: utf-8 -*-
"""
溫和整表校準：整張表都可調整，使 RTP 逼近 96.80%。
公式：V' = V * scale（整格等比放大），再限制在 [40, 177]（官方規則 0.4～1.77 倍，主注 100）。
註：若用 V' = 100 + (V-100)*scale，scale>1 會把低於 100 的格壓更低，多數兌現為劣勢會導致 RTP 下降。
"""
import os
import sys
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
SMOOTH_PATH = os.path.join(DATA_DIR, "blackjack 對照表 - 平滑推算表.csv")
TARGET_RTP = 96.80
# 官方規則：兌現賠付 0.4～1.77 倍，主注 100 → 40～177 元
V_MIN, V_MAX = 40, 177

CALIBRATION_ROUNDS = int(os.environ.get("CALIBRATION_ROUNDS", "2000000"))
MAX_SCALE_ITERATIONS = 8
RTP_TOLERANCE = 0.05  # 與目標差距小於 0.15% 即停止


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


def load_smooth_tables():
    """載入當前平滑推算表（三個區塊）。"""
    df_hard = pd.read_csv(SMOOTH_PATH, skiprows=1, nrows=15, index_col=0)
    df_soft = pd.read_csv(SMOOTH_PATH, skiprows=19, nrows=9, index_col=0)
    df_split = pd.read_csv(SMOOTH_PATH, skiprows=32, nrows=12, index_col=0)
    df_hard = _normalize_columns(df_hard)
    df_soft = _normalize_columns(df_soft)
    df_split = _normalize_columns(df_split)
    return {"hard": df_hard, "soft": df_soft, "split": df_split}


def apply_gentle_scale(tables, scale, v_min=V_MIN, v_max=V_MAX):
    """
    對整張表做等比縮放：V' = V * scale，再限制在 [v_min, v_max]。
    scale > 1 時每格都變大，RTP 上升；限制在 40～177 符合官方規則。
    """
    out = {}
    for block in ("hard", "soft", "split"):
        df = tables[block].copy()
        for idx in df.index:
            for col in df.columns:
                try:
                    v = float(df.loc[idx, col])
                    new_v = v * scale
                    df.loc[idx, col] = max(v_min, min(v_max, round(new_v, 0)))
                except (TypeError, ValueError):
                    pass
        out[block] = df
    return out


def _get_rtp_module():
    from importlib.util import spec_from_file_location, module_from_spec
    spec = spec_from_file_location("rtp", os.path.join(SCRIPT_DIR, "cash out RTP.py"))
    rtp_module = module_from_spec(spec)
    spec.loader.exec_module(rtp_module)
    return rtp_module


def run_simulation(tables, n_rounds, seed=42):
    rtp_module = _get_rtp_module()
    _, _, rtp_pct = rtp_module.run_simulation(tables, int(n_rounds), seed=seed)
    return rtp_pct


def write_smooth_csv(path, tables):
    def _write_block(f, title, df):
        f.write(title + "\n")
        f.write("您的點數 \\ 莊家," + ",".join(
            "A (11)" if c == 11 else str(c) for c in df.columns
        ) + "\n")
        for idx in df.index:
            row_vals = [
                str(int(round(float(df.loc[idx, c])))) if pd.notna(df.loc[idx, c]) else ""
                for c in df.columns
            ]
            idx_str = str(idx)
            if "," in idx_str:
                idx_str = '"' + idx_str + '"'
            f.write(idx_str + "," + ",".join(row_vals) + "\n")

    with open(path, "w", encoding="utf-8") as f:
        _write_block(f, "硬牌,,,,,,,,,,", tables["hard"])
        f.write(",,,,,,,,,,\n")
        _write_block(f, "軟牌,,,,,,,,,,", tables["soft"])
        f.write(",,,,,,,,,,\n")
        f.write(",,,,,,,,,,\n")
        _write_block(f, "分牌,,,,,,,,,,", tables["split"])


def main():
    print("載入平滑推算表（backup 或目前表格）...")
    tables_base = load_smooth_tables()

    print(f"目標 RTP: {TARGET_RTP}%")
    print(f"兌現賠付限制: [{V_MIN}, {V_MAX}]（0.4～1.77 倍，主注 100）")
    print(f"校準模擬局數: {CALIBRATION_ROUNDS}")
    print("估計當前 RTP...")
    current_rtp = run_simulation(tables_base, CALIBRATION_ROUNDS)
    print(f"  當前 RTP: {current_rtp:.2f}%")

    # 迭代搜尋 scale（V'=V*scale）：scale 大則 RTP 大，依結果微調
    scale = TARGET_RTP / current_rtp
    tables_calibrated = None
    for it in range(MAX_SCALE_ITERATIONS):
        tables_calibrated = apply_gentle_scale(tables_base, scale)
        rtp_after = run_simulation(tables_calibrated, CALIBRATION_ROUNDS)
        err = TARGET_RTP - rtp_after
        print(f"  迭代 {it + 1}: scale={scale:.4f} → RTP={rtp_after:.2f}% (差 {err:+.2f}%)")
        if abs(err) <= RTP_TOLERANCE:
            break
        if rtp_after <= 0:
            break
        # 依差距調整 scale（從原始表重算，避免累積誤差）
        scale *= (TARGET_RTP / rtp_after)
        scale = max(0.5, min(scale, 2.0))

    backup_path = os.path.join(DATA_DIR, "blackjack 對照表 - 平滑推算表.backup.csv")
    if os.path.exists(SMOOTH_PATH):
        import shutil
        shutil.copy(SMOOTH_PATH, backup_path)
        print(f"  已備份原表至: {backup_path}")

    write_smooth_csv(SMOOTH_PATH, tables_calibrated)
    print(f"已寫入校準後平滑推算表: {SMOOTH_PATH}")
    print("請再執行「cash out RTP.py」用 1000 萬局驗證 RTP。")


if __name__ == "__main__":
    main()
