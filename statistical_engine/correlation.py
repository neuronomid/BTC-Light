import numpy as np
import pandas as pd
from typing import Dict
from loguru import logger

class CorrelationAnalyzer:
    def __init__(self):
        pass

    def analyze(self, df: pd.DataFrame, external: Dict[str, pd.DataFrame] = None) -> Dict:
        returns = np.log(df["close"] / df["close"].shift(1)).dropna()
        if len(returns) < 30:
            logger.warning(f"Correlation needs >=30 returns, got {len(returns)}")
            return {}
        results = {
            "corr_btc_spx_30d": None,
            "corr_btc_dxy_30d": None,
            "corr_btc_gold_30d": None,
            "corr_btc_eth_30d": None,
            "tail_dependence_btc_spx": None,
            "dcc_garch_btc_spx": None,
            "risk_on_off_regime": "UNKNOWN"
        }
        if external:
            for key, edf in external.items():
                if edf is None or edf.empty:
                    continue
                er = np.log(edf["close"] / edf["close"].shift(1)).dropna()
                aligned = pd.concat([returns, er], axis=1).dropna()
                if len(aligned) < 30:
                    continue
                corr_30 = aligned.iloc[-30:].corr().iloc[0, 1]
                results[f"corr_{key}_30d"] = round(float(corr_30), 4) if not np.isnan(corr_30) else None
                # simple tail dependence proxy: correlation of extreme moves
                thresh = aligned.quantile(0.95)
                extreme = aligned[(aligned.iloc[:, 0] > thresh.iloc[0]) | (aligned.iloc[:, 1] > thresh.iloc[1])]
                if len(extreme) > 5:
                    td = extreme.corr().iloc[0, 1]
                    if key == "btc_spx":
                        results["tail_dependence_btc_spx"] = round(float(td), 4)
        # Risk-on/off heuristic
        spx_corr = results.get("corr_btc_spx_30d", 0)
        dxy_corr = results.get("corr_btc_dxy_30d", 0)
        if spx_corr is not None and spx_corr > 0.3 and dxy_corr is not None and dxy_corr < -0.1:
            results["risk_on_off_regime"] = "RISK_ON"
        elif spx_corr is not None and spx_corr < -0.1:
            results["risk_on_off_regime"] = "RISK_OFF"
        else:
            results["risk_on_off_regime"] = "MIXED"
        return results
