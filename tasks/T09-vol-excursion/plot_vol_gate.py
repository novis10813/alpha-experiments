"""Figures for T09 vol-gate-v1 from its output tables.

  python -m tasks.T09-vol-excursion.plot_vol_gate summary [--estimator rv_60]
      F2 bins, F3 gate curves, F4 cumulative daily IC, F5 cross-instrument heat maps, F6 z quantiles.
  python -m tasks.T09-vol-excursion.plot_vol_gate window --inst BTC --start 2026-08-01 --end 2026-08-03
      [--h 60] [--estimator rv_60] [--threshold 40]
      F1 time series: mid, expected move x = sigma sqrt(h) with the gate shaded, realized forward R and |r_h|.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .observe_vol_gate import ESTIMATORS, HS, OUT, targets

INSTS = ("BTC", "ETH", "BNB")
FIG = OUT / "figures"
RW = np.sqrt(2 / np.pi)  # E|N(0, s)| / s


def costs() -> dict[str, dict[str, float]]:
    run = json.loads((OUT / "run.json").read_text())
    return {k[:3]: v["cost_bps"] for k, v in run["instruments"].items()}


def blocks() -> dict[str, list[str]]:
    run = json.loads((OUT / "run.json").read_text())
    return {k[:3]: v["blocks"] for k, v in run["instruments"].items()}


def grid(title: str, sharey: bool = False):
    fig, axes = plt.subplots(len(INSTS), len(HS), figsize=(5 * len(HS), 3.6 * len(INSTS)), squeeze=False,
                             sharey=sharey)
    fig.suptitle(title)
    for i, inst in enumerate(INSTS):
        for j, h in enumerate(HS):
            axes[i, j].set_title(f"{inst} h={h}")
            axes[i, j].grid(alpha=0.3)
    return fig, axes


def cost_lines(ax, c: dict[str, float]) -> None:
    ax.axhline(c["v1"], color="red", ls="--", lw=1, label=f"cost v1 {c['v1']:.1f}")
    ax.axhline(c["v2"], color="orange", ls="--", lw=1, label=f"cost v2 {c['v2']:.1f}")


def save(fig, name: str) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIG / name, dpi=110)
    plt.close(fig)
    print(FIG / name)


def f2_bins(est: str) -> None:
    d, c, bl = pd.read_csv(OUT / "o1_bins.csv"), costs(), blocks()
    fig, axes = grid(f"F2 mean |r_h| by expected move x = sigma sqrt(h), estimator {est} (band: 5-95% day bootstrap)")
    for i, inst in enumerate(INSTS):
        for j, h in enumerate(HS):
            ax, g = axes[i, j], d[(d.inst == inst) & (d.h == h) & (d.estimator == est)]
            ax.fill_between(g.x_mean, g.abs_r_ci_lo, g.abs_r_ci_hi, alpha=0.25, color="C0")
            ax.plot(g.x_mean, g.abs_r_mean, "o-", color="C0", label="all")
            ax.plot(g.x_mean, g.R_mean, "s:", color="C2", label="mean R")
            for k, bk in enumerate(bl[inst]):
                ok = g[f"n_{bk}"] >= 100
                ax.plot(g.x_mean[ok], g[f"abs_r_{bk}"][ok], lw=0.8, alpha=0.7, color=f"C{k + 3}", label=bk)
            lim = float(g.x_mean.max()) * 1.05
            ax.plot([0, lim], [0, RW * lim], color="grey", lw=0.6, label="random walk: E|r_h| = 0.80 x")
            cost_lines(ax, c[inst])
            ax.set_xlabel("x (bps)")
            ax.set_ylabel("bps")
    axes[0, -1].legend(fontsize=7)
    save(fig, f"F2_bins_{est}.png")


def f3_gate(cost: str) -> None:
    d = pd.read_csv(OUT / "o1_gate.csv")
    fig, axes = grid(f"F3 breakeven hit rate p* ({cost}) vs share of time the gate is open")
    for i, inst in enumerate(INSTS):
        for j, h in enumerate(HS):
            ax = axes[i, j]
            for e in ESTIMATORS:
                g = d[(d.inst == inst) & (d.h == h) & (d.estimator == e)]
                ax.plot(g.coverage, g[f"p_star_{cost}"].clip(upper=1.05), label=e)
            ax.set_xscale("log")
            ax.set_ylim(0.5, 1.05)
            ax.axhline(1.0, color="grey", lw=0.6)
            ax.set_xlabel("coverage (share of minutes with x >= X)")
            ax.set_ylabel("p*")
    axes[0, -1].legend(fontsize=7)
    save(fig, f"F3_gate_{cost}.png")


def f3_threshold(est: str) -> None:
    d, bl = pd.read_csv(OUT / "o1_gate.csv"), blocks()
    fig, axes = grid(f"F3b gate threshold X vs p* and coverage, estimator {est}")
    for i, inst in enumerate(INSTS):
        for j, h in enumerate(HS):
            ax, g = axes[i, j], d[(d.inst == inst) & (d.h == h) & (d.estimator == est)]
            for cost, col in (("v1", "red"), ("v2", "orange")):
                ax.plot(g.X, g[f"p_star_{cost}"].clip(upper=1.05), color=col, label=f"p* {cost}")
            ax.set_ylim(0.5, 1.05)
            ax.set_xlabel("X (bps)")
            ax2 = ax.twinx()
            ax2.plot(g.X, g.coverage, color="black", lw=1, label="coverage")
            for k, bk in enumerate(bl[inst]):
                ax2.plot(g.X, g[f"coverage_{bk}"], lw=0.6, alpha=0.6, color=f"C{k + 3}")
            ax2.set_yscale("log")
            ax2.set_ylabel("coverage")
    axes[0, -1].legend(fontsize=7, loc="lower right")
    save(fig, f"F3b_threshold_{est}.png")


def f4_ic() -> None:
    d = pd.read_csv(OUT / "o1_ic.csv")
    fig, axes = grid("F4 cumulative daily Spearman IC of sigma with |r_h| (legend: IR)")
    for i, inst in enumerate(INSTS):
        for j, h in enumerate(HS):
            ax = axes[i, j]
            for e in ESTIMATORS:
                r = d[(d.inst == inst) & (d.h == h) & (d.estimator == e)].iloc[0]
                s = pd.Series(json.loads(r.daily_ic))
                ax.plot(pd.to_datetime(s.index), s.cumsum().to_numpy(), label=f"{e} {r.ic_ir:.2f}")
            ax.legend(fontsize=7)
            ax.tick_params(axis="x", labelrotation=30)
    save(fig, "F4_daily_ic.png")


def f5_heat(est: str) -> None:
    d = pd.read_csv(OUT / "o3_heat.csv")
    for h in HS:
        fig, axes = plt.subplots(len(INSTS), 2, figsize=(10, 3.6 * len(INSTS)), squeeze=False)
        fig.suptitle(f"F5 mean |r_h| (bps), own x by source x, estimator {est}, h={h}")
        for i, inst in enumerate(INSTS):
            for j, src in enumerate(s for s in INSTS if s != inst):
                ax = axes[i, j]
                g = d[(d.inst == inst) & (d.h == h) & (d.estimator == est) & (d.source == src)]
                m = g.pivot(index="own_lo", columns="src_lo", values="abs_r_mean")
                n = g.pivot(index="own_lo", columns="src_lo", values="n")
                ax.imshow(m.to_numpy(), origin="lower", cmap="viridis", aspect="auto")
                for (a, b), v in np.ndenumerate(m.to_numpy()):
                    if np.isfinite(v):
                        ax.text(b, a, f"{v:.1f}\nn={int(n.iat[a, b])}", ha="center", va="center", fontsize=7,
                                color="white")
                ax.set_xticks(range(m.shape[1]), [f">={v:g}" for v in m.columns])
                ax.set_yticks(range(m.shape[0]), [f">={v:g}" for v in m.index])
                ax.set_xlabel(f"{src} x (bps)")
                ax.set_ylabel(f"{inst} own x (bps)")
        save(fig, f"F5_cross_{est}_h{h}.png")


def f6_z(est: str) -> None:
    d = pd.read_csv(OUT / "o4_z.csv")
    fig, axes = grid(f"F6 R / x and |r_h| / x by expected move x, estimator {est} (median, 25-75%)")
    for i, inst in enumerate(INSTS):
        for j, h in enumerate(HS):
            ax, g = axes[i, j], d[(d.inst == inst) & (d.h == h) & (d.estimator == est)]
            lab = [f"{lo:g}" for lo in g.bin_lo]
            pos = np.arange(len(g))
            for col, c in (("z_R", "C2"), ("z_abs", "C0")):
                ax.plot(pos, g[f"{col}_q50"], "o-", color=c, label=col)
                ax.fill_between(pos, g[f"{col}_q25"], g[f"{col}_q75"], alpha=0.2, color=c)
            ax.axhline(1.0, color="grey", lw=0.6)
            ax.set_xticks(pos, lab, fontsize=7)
            ax.set_xlabel("x bin lower edge (bps)")
    axes[0, -1].legend(fontsize=7)
    save(fig, f"F6_z_{est}.png")


def f1_window(inst: str, start: str, end: str, h: int, est: str, threshold: float) -> None:
    f = pd.read_parquet(OUT / f"features_{inst}.parquet")
    abs_r, R = targets(f.mid.to_numpy(dtype=float), h)
    t = pd.to_datetime(f.index, utc=True)
    m = (t >= pd.Timestamp(start, tz="UTC")) & (t < pd.Timestamp(end, tz="UTC"))
    t, f, abs_r, R = t[m], f[m], abs_r[m], R[m]
    x = f[est].to_numpy() * np.sqrt(h)
    c = costs()[inst]
    fig, ax = plt.subplots(3, 1, figsize=(14, 9), sharex=True)
    fig.suptitle(f"F1 {inst} {start} to {end}, estimator {est}, h={h}, gate x >= {threshold:g} bps")
    ax[0].plot(t, f.mid, lw=0.8)
    ax[0].set_ylabel("mid")
    ax[1].plot(t, x, lw=0.8, label="x = sigma sqrt(h), known at t")
    ax[1].axhline(threshold, color="black", lw=0.8, label="gate X")
    ax[2].plot(t, R, lw=0.6, color="C2", label="R over (t, t+h], realized later")
    ax[2].plot(t, abs_r, lw=0.6, color="C0", alpha=0.7, label="|r_h|, realized later")
    for a in ax[1:]:
        cost_lines(a, c)
        a.set_ylabel("bps")
        a.legend(fontsize=7, loc="upper right")
    gate = x >= threshold
    for a in ax:
        a.fill_between(t, 0, 1, where=gate, transform=a.get_xaxis_transform(), color="gold", alpha=0.25, lw=0)
        a.grid(alpha=0.3)
    save(fig, f"F1_{inst}_{start}_{end}_{est}_h{h}.png")


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("summary")
    s.add_argument("--estimator", default="rv_60", choices=ESTIMATORS)
    w = sub.add_parser("window")
    w.add_argument("--inst", required=True, choices=INSTS)
    w.add_argument("--start", required=True)
    w.add_argument("--end", required=True)
    w.add_argument("--h", type=int, default=60, choices=HS)
    w.add_argument("--estimator", default="rv_60", choices=ESTIMATORS)
    w.add_argument("--threshold", type=float, default=40.0)
    a = p.parse_args()
    if a.cmd == "summary":
        f2_bins(a.estimator)
        f3_gate("v1")
        f3_gate("v2")
        f3_threshold(a.estimator)
        f4_ic()
        f5_heat(a.estimator)
        f6_z(a.estimator)
    else:
        f1_window(a.inst, a.start, a.end, a.h, a.estimator, a.threshold)


if __name__ == "__main__":
    main()
