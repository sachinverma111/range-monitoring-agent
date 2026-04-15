#!/usr/bin/env python3
"""
Range Monitoring Agent — CLI entry point.

Usage:
    python main.py
    python main.py --products sample_data/products.csv \\
                   --online sample_data/online_sales.csv \\
                   --stores sample_data/store_sales.csv \\
                   --calendar sample_data/calendar.csv \\
                   --config configs/default.yaml \\
                   --output output/
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Range Monitoring Agent — surfaces product range mismatches across retail locations."
    )
    parser.add_argument("--products", default="sample_data/products.csv", help="Path to product master CSV/XLSX")
    parser.add_argument("--online", default="sample_data/online_sales.csv", help="Path to online sales CSV/XLSX")
    parser.add_argument("--stores", default="sample_data/store_sales.csv", help="Path to store sales CSV/XLSX")
    parser.add_argument("--calendar", default="sample_data/calendar.csv", help="Path to business calendar CSV/XLSX (optional)")
    parser.add_argument("--config", default="configs/default.yaml", help="Path to config YAML")
    parser.add_argument("--output", default="output", help="Output directory for report and JSON")
    parser.add_argument("--top", type=int, default=10, help="Number of insights to print to console (default: 10)")
    args = parser.parse_args()

    # ---- Imports (deferred so CLI --help is fast) ----
    from range_monitor.config import load_config
    from range_monitor.delivery import build_narratives, render_console_summary, save_outputs
    from range_monitor.engine import run_analysis
    from range_monitor.ingestion import load_calendar, load_online_sales, load_products, load_store_sales

    run_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n{'='*60}")
    print(f"  Range Monitoring Agent")
    print(f"  Run date: {run_date}")
    print(f"{'='*60}\n")

    # ---- Load config ----
    print(f"Loading config from: {args.config}")
    config = load_config(args.config)

    # ---- Load data ----
    print(f"Loading data files...")
    try:
        products = load_products(args.products)
        print(f"  Products:      {len(products)} records")
        online_sales = load_online_sales(args.online)
        print(f"  Online sales:  {len(online_sales)} records")
        store_sales = load_store_sales(args.stores)
        print(f"  Store sales:   {len(store_sales)} records")
        calendar = None
        if args.calendar and Path(args.calendar).exists():
            calendar = load_calendar(args.calendar)
            print(f"  Calendar:      {len(calendar)} records")
    except (FileNotFoundError, ValueError) as e:
        print(f"\nError loading data: {e}", file=sys.stderr)
        sys.exit(1)

    # ---- Run analysis ----
    print(f"\nRunning analysis ({', '.join(config.enabled_rules)})...")
    insights = run_analysis(products, online_sales, store_sales, calendar, config)
    print(f"  {len(insights)} insights generated (top {config.top_insights_count} shown)")

    if not insights:
        print("\nNo insights generated. Try lowering thresholds in the config file.")
        return

    # ---- Build narratives ----
    insights = build_narratives(insights)

    # ---- Console output ----
    print(f"\n{'='*60}")
    print(f"  Top {min(args.top, len(insights))} Insights")
    print(f"{'='*60}\n")
    print(render_console_summary(insights, top_n=args.top))

    # ---- Save outputs ----
    print(f"\nSaving full report to {args.output}/...")
    save_outputs(insights, config, output_dir=args.output, run_date=run_date)

    print(f"\nDone.\n")


if __name__ == "__main__":
    main()
