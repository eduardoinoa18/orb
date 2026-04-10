"""Lightweight server-rendered UI shell for ORB local development.

This keeps a useful visual interface available before the React dashboard is
fully integrated. The API remains the source of truth; these pages are only a
simple control surface and status view.
"""

from html import escape
from typing import Any


def _page(title: str, body: str) -> str:
    """Wraps page content in a shared ORB layout and CSS theme."""
    safe_title = escape(title)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{safe_title}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
  <style>
    :root {{
      --orb-50: #E6F1FB;
      --orb-400: #378ADD;
      --orb-600: #185FA5;
      --orb-900: #042C53;

      --surface-0: #07080c;
      --surface-1: #0d0f17;
      --surface-2: #111520;
      --surface-3: #181c2a;
      --surface-4: #1e2333;

      --border-subtle: rgba(255,255,255,0.06);
      --border-default: rgba(255,255,255,0.10);
      --border-strong: rgba(255,255,255,0.18);

      --text-primary: #f0f2f8;
      --text-secondary: #8b92a8;
      --text-tertiary: #4a5070;
      --text-inverse: #07080c;

      --success: #22c55e;
      --warning: #f59e0b;
      --danger: #ef4444;
      --info: #3b82f6;

      --font-sans: 'Inter', -apple-system, sans-serif;
      --font-mono: 'JetBrains Mono', 'Fira Code', monospace;

      --radius-xs: 4px;
      --radius-sm: 6px;
      --radius-md: 8px;
      --radius-lg: 12px;
      --radius-xl: 16px;
      --radius-2xl: 20px;
      --radius-full: 9999px;

      --shadow-sm: 0 1px 2px rgba(0,0,0,0.4);
      --shadow-md: 0 4px 12px rgba(0,0,0,0.5);
      --shadow-lg: 0 8px 24px rgba(0,0,0,0.6);

      --transition-instant: 80ms ease;
      --transition-fast: 150ms ease;
      --transition-base: 250ms ease;
      --transition-slow: 400ms ease;

      --bg: var(--surface-0);
      --ink: var(--text-primary);
      --muted: var(--text-secondary);
      --brand: var(--orb-600);
      --brand-light: var(--orb-400);
      --panel: var(--surface-2);
      --line: var(--border-default);
      --ok: var(--success);
      --warn: var(--warning);
      --success-bg: rgba(34, 197, 94, 0.18);
      --warn-bg: rgba(245, 158, 11, 0.18);
      --radius: var(--radius-lg);
    }}

    * {{ box-sizing: border-box; }}

    body {{
      margin: 0;
      color: var(--ink);
      font-family: var(--font-sans);
      background:
        radial-gradient(circle at 18% 0%, rgba(24, 95, 165, 0.22), transparent 35%),
        radial-gradient(circle at 90% 0%, rgba(59, 130, 246, 0.14), transparent 32%),
        linear-gradient(180deg, #090b11 0%, var(--bg) 28%);
      min-height: 100vh;
      line-height: 1.5;
    }}

    .shell {{
      max-width: 1320px;
      margin: 0 auto;
      padding: 24px 20px 48px;
    }}

    .app-layout {{
      display: grid;
      grid-template-columns: 220px minmax(0, 1fr);
      min-height: 100vh;
    }}

    .sidebar {{
      position: sticky;
      top: 0;
      height: 100vh;
      padding: 18px 14px;
      background: rgba(13, 15, 23, 0.95);
      border-right: 1px solid var(--border-subtle);
      display: flex;
      flex-direction: column;
      gap: 18px;
    }}

    .sidebar-brand {{
      padding: 8px 10px 14px;
      border-bottom: 1px solid var(--border-subtle);
    }}

    .sidebar-brand .wordmark {{
      margin: 0;
      color: var(--orb-400);
      font-size: 22px;
      font-weight: 700;
      letter-spacing: 0.06em;
    }}

    .sidebar-brand .version {{
      margin-top: 4px;
      color: var(--text-tertiary);
      font-size: 11px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}

    .sidebar-section {{
      display: grid;
      gap: 6px;
    }}

    .sidebar-label {{
      color: var(--text-tertiary);
      font-size: 11px;
      font-weight: 500;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      padding: 0 10px;
    }}

    .sidebar-link {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 10px 12px;
      border-radius: var(--radius-md);
      color: var(--text-secondary);
      text-decoration: none;
      border: 1px solid transparent;
      transition: all var(--transition-fast);
      position: relative;
    }}

    .sidebar-link:hover {{
      color: var(--text-primary);
      background: var(--surface-3);
      border-color: var(--border-default);
    }}

    .sidebar-link.active {{
      color: var(--text-primary);
      background: rgba(24,95,165,0.12);
      border-color: rgba(24,95,165,0.28);
      box-shadow: inset 2px 0 0 var(--orb-600);
    }}

    .sidebar-link-main {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      min-width: 0;
    }}

    .sidebar-icon {{
      width: 20px;
      text-align: center;
      color: var(--text-tertiary);
      font-size: 14px;
    }}

    .sidebar-link.active .sidebar-icon,
    .sidebar-link:hover .sidebar-icon {{
      color: var(--orb-400);
    }}

    .sidebar-status-dot {{
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: var(--text-tertiary);
      box-shadow: 0 0 0 0 currentColor;
    }}

    .sidebar-status-dot.live {{
      color: var(--success);
      background: var(--success);
      animation: status-pulse 2s infinite;
    }}

    .sidebar-footer {{
      margin-top: auto;
      border-top: 1px solid var(--border-subtle);
      padding-top: 14px;
      display: grid;
      gap: 10px;
    }}

    .profile-card {{
      background: var(--surface-2);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-lg);
      padding: 12px;
      display: flex;
      align-items: center;
      gap: 10px;
    }}

    .profile-avatar {{
      width: 34px;
      height: 34px;
      border-radius: 999px;
      display: grid;
      place-items: center;
      background: linear-gradient(135deg, var(--orb-600), var(--orb-400));
      color: #fff;
      font-weight: 600;
      font-size: 13px;
    }}

    .profile-meta {{
      min-width: 0;
    }}

    .profile-meta strong {{
      display: block;
      font-size: 13px;
      font-weight: 500;
    }}

    .profile-meta span {{
      display: block;
      font-size: 11px;
      color: var(--text-tertiary);
    }}

    .content-shell {{
      min-width: 0;
      padding-bottom: 88px;
    }}

    .mobile-nav {{
      display: none;
      position: fixed;
      left: 12px;
      right: 12px;
      bottom: 12px;
      z-index: 50;
      background: rgba(13, 15, 23, 0.94);
      border: 1px solid var(--border-default);
      border-radius: 18px;
      box-shadow: var(--shadow-lg);
      padding: 8px;
      grid-template-columns: repeat(5, 1fr);
      gap: 6px;
      backdrop-filter: blur(10px);
    }}

    .mobile-nav a {{
      text-decoration: none;
      color: var(--text-secondary);
      font-size: 11px;
      text-align: center;
      padding: 8px 4px;
      border-radius: 12px;
      border: 1px solid transparent;
      transition: all var(--transition-fast);
    }}

    .mobile-nav a.active {{
      color: var(--text-primary);
      background: rgba(24,95,165,0.16);
      border-color: rgba(24,95,165,0.28);
    }}

    .topbar-actions {{
      display: flex;
      gap: 10px;
      align-items: center;
    }}

    .icon-btn {{
      position: relative;
      border: 1px solid var(--border-default);
      background: var(--surface-2);
      color: var(--text-secondary);
      border-radius: var(--radius-md);
      padding: 9px 12px;
      cursor: pointer;
      font-size: 13px;
      font-weight: 500;
      transition: all var(--transition-fast);
    }}

    .icon-btn:hover {{
      color: var(--text-primary);
      background: var(--surface-3);
      border-color: var(--border-strong);
    }}

    .notif-badge {{
      position: absolute;
      top: -6px;
      right: -6px;
      min-width: 18px;
      height: 18px;
      padding: 0 5px;
      border-radius: 999px;
      background: var(--danger);
      color: white;
      font-size: 10px;
      font-weight: 700;
      display: grid;
      place-items: center;
    }}

    .overlay-panel {{
      position: fixed;
      top: 16px;
      right: 16px;
      width: min(360px, calc(100vw - 24px));
      max-height: calc(100vh - 32px);
      overflow: auto;
      z-index: 70;
      background: rgba(13, 15, 23, 0.97);
      border: 1px solid var(--border-default);
      border-radius: 18px;
      box-shadow: var(--shadow-lg);
      padding: 14px;
      backdrop-filter: blur(10px);
      display: none;
    }}

    .overlay-panel.open {{
      display: block;
    }}

    .overlay-panel h4 {{
      margin: 0 0 8px;
      font-size: 14px;
      font-weight: 600;
    }}

    .overlay-list {{
      display: grid;
      gap: 10px;
      margin-top: 10px;
    }}

    .overlay-item {{
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-lg);
      background: var(--surface-2);
      padding: 12px;
    }}

    .overlay-item strong {{
      display: block;
      font-size: 13px;
      margin-bottom: 4px;
    }}

    .right-tray-grid {{
      display: grid;
      gap: 10px;
      margin-top: 10px;
    }}

    .tray-tile {{
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-lg);
      background: var(--surface-2);
      padding: 12px;
    }}

    .brain-card-grid,
    .improvement-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
      margin-top: 10px;
    }}

    .brain-card,
    .improvement-card {{
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-lg);
      background: var(--surface-3);
      padding: 14px;
      transition: all var(--transition-fast);
    }}

    .brain-card:hover,
    .improvement-card:hover {{
      border-color: var(--border-strong);
      transform: translateY(-1px);
    }}

    .brain-card h4,
    .improvement-card h4 {{
      margin: 0 0 6px;
      font-size: 13px;
      font-weight: 600;
    }}

    .brain-models {{
      margin-top: 8px;
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }}

    .mini-mode-row {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 10px;
    }}

    .metric-delta {{
      color: var(--text-secondary);
      font-size: 12px;
      font-family: var(--font-mono);
      margin-top: 6px;
    }}

    .topbar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 28px;
      gap: 24px;
      flex-wrap: wrap;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--border-subtle);
      position: sticky;
      top: 0;
      z-index: 30;
      background: rgba(7, 8, 12, 0.78);
      backdrop-filter: blur(8px);
    }}

    .brand {{
      font-size: 22px;
      font-weight: 700;
      letter-spacing: 0.1px;
      color: var(--orb-400);
      margin: 0;
      display: flex;
      align-items: center;
      gap: 8px;
    }}

    .brand::before {{
      content: "◆";
      font-size: 20px;
    }}

    .nav {{
      display: flex;
      gap: 4px;
      flex-wrap: wrap;
    }}

    .nav a {{
      text-decoration: none;
      color: var(--text-secondary);
      background: transparent;
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-md);
      padding: 10px 16px;
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      transition: all var(--transition-fast);
    }}

    .nav a:hover {{
      color: var(--text-primary);
      background: var(--surface-3);
      border-color: var(--border-default);
      box-shadow: var(--shadow-md);
    }}

    .hero {{
      background: linear-gradient(135deg, #113157 0%, #185FA5 45%, #226bb6 100%);
      color: #ffffff;
      border-radius: var(--radius-xl);
      padding: 32px;
      box-shadow: var(--shadow-lg);
      margin-bottom: 28px;
      border: 1px solid rgba(255, 255, 255, 0.12);
    }}

    .hero h1 {{
      margin: 0 0 12px;
      font-size: 28px;
      font-weight: 600;
      letter-spacing: -0.5px;
    }}

    .hero p {{
      margin: 0 0 16px;
      opacity: 0.98;
      max-width: 72ch;
      font-size: 15px;
      line-height: 1.6;
    }}

    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
      margin-top: 16px;
    }}

    .panel {{
      background: var(--panel);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-lg);
      padding: 20px;
      box-shadow: var(--shadow-sm);
      transition: all var(--transition-base);
    }}

    .panel:hover {{
      box-shadow: var(--shadow-md);
      border-color: var(--border-default);
      transform: translateY(-1px);
    }}

    .panel h3 {{
      margin: 0 0 12px;
      font-size: 13px;
      font-weight: 500;
      color: var(--ink);
      letter-spacing: 0.02em;
    }}

    .panel p {{
      margin: 0 0 12px;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.5;
    }}

    .panel p:last-child {{ margin-bottom: 0; }}

    .kpi {{
      font-size: 28px;
      font-weight: 600;
      margin: 8px 0 0;
      color: var(--text-primary);
      font-variant-numeric: tabular-nums;
    }}

    .kpi.ok {{ color: var(--ok); }}
    .kpi.warn {{ color: var(--warn); }}

    .list {{
      margin: 0;
      padding-left: 20px;
      color: var(--muted);
      font-size: 14px;
    }}

    .list li {{
      margin: 6px 0;
      line-height: 1.5;
    }}

    .footer {{
      margin-top: 24px;
      color: var(--muted);
      font-size: 13px;
    }}

    .badge {{
      display: inline-block;
      font-size: 12px;
      border-radius: var(--radius-full);
      border: 1px solid rgba(24, 95, 165, 0.45);
      color: var(--orb-50);
      padding: 6px 12px;
      background: rgba(24, 95, 165, 0.28);
      font-weight: 600;
      margin-top: 12px;
    }}

    code {{
      background: var(--surface-1);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-xs);
      padding: 2px 6px;
      font-family: var(--font-mono);
      font-size: 12px;
      color: #7dd3fc;
    }}

    .action-btn {{
      border: 1px solid transparent;
      background: var(--orb-600);
      color: #ffffff;
      border-radius: var(--radius-md);
      padding: 8px 16px;
      font-weight: 500;
      cursor: pointer;
      font-size: 13px;
      transition: all var(--transition-fast);
      box-shadow: var(--shadow-sm);
    }}

    .action-btn:hover {{
      background: var(--orb-400);
      box-shadow: var(--shadow-md);
      transform: translateY(-1px);
    }}

    .action-btn:active {{
      transform: scale(0.97);
    }}

    .action-btn:focus-visible {{
      outline: 2px solid var(--orb-400);
      outline-offset: 2px;
    }}

    .action-input {{
      padding: 10px 12px;
      border: 1px solid var(--border-default);
      border-radius: var(--radius-md);
      width: 100%;
      font-size: 13px;
      font-family: var(--font-sans);
      transition: all var(--transition-fast);
      background: var(--surface-1);
      color: var(--text-primary);
    }}

    .action-input:focus {{
      outline: none;
      border-color: var(--orb-600);
      box-shadow: 0 0 0 3px rgba(24,95,165,0.15);
    }}

    .action-input::placeholder {{
      color: var(--text-tertiary);
    }}

    .table-wrap {{
      overflow: auto;
      border-radius: 8px;
      border: 1px solid var(--line);
    }}

    .agents-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}

    .agents-table th {{
      background: var(--surface-3);
      text-align: left;
      border-bottom: 1px solid var(--line);
      padding: 12px;
      font-weight: 600;
      color: var(--ink);
    }}

    .agents-table td {{
      text-align: left;
      border-bottom: 1px solid var(--line);
      padding: 12px;
      vertical-align: top;
    }}

    .agents-table tr:hover {{
      background: var(--surface-3);
    }}

    .stat-strip {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 12px;
      margin-bottom: 12px;
    }}

    .stat-tile {{
      border: 1px solid var(--line);
      border-radius: var(--radius-md);
      padding: 12px;
      background: var(--surface-3);
      transition: all var(--transition-fast);
    }}

    .stat-tile:hover {{
      background: var(--surface-4);
      border-color: var(--border-strong);
    }}

    .stat-tile .label {{
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 6px;
      font-weight: 500;
    }}

    .stat-tile .value {{
      color: var(--text-primary);
      font-size: 20px;
      font-weight: 500;
      font-variant-numeric: tabular-nums;
      line-height: 1.1;
    }}

    .mini-wrap {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }}

    .mini-panel {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: var(--surface-3);
    }}

    .mini-title {{
      margin: 0 0 10px;
      font-size: 14px;
      color: var(--ink);
      font-weight: 600;
    }}

    .mini-list {{
      margin: 0;
      padding-left: 18px;
      color: var(--muted);
      font-size: 13px;
      max-height: 220px;
      overflow: auto;
      line-height: 1.5;
    }}

    .mini-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
    }}

    .mini-table th,
    .mini-table td {{
      text-align: left;
      border-bottom: 1px solid var(--line);
      padding: 8px;
      vertical-align: top;
    }}

    .chip {{
      display: inline-block;
      border-radius: 14px;
      padding: 4px 10px;
      font-size: 11px;
      font-weight: 600;
      line-height: 1.4;
      border: 1px solid transparent;
      text-transform: capitalize;
    }}

    .chip-hot {{ background: #ffeceb; color: #a30b0b; border-color: #ffccc7; }}
    .chip-warm {{ background: #fff8e1; color: #b8860b; border-color: #f0d29a; }}
    .chip-cold {{ background: #e3f2fd; color: #0d47a1; border-color: #bbdefb; }}
    .chip-ok {{ background: var(--success-bg); color: var(--ok); border-color: #bbf7d0; }}
    .chip-pending {{ background: var(--warn-bg); color: var(--warn); border-color: #fce8b6; }}
    .chip-muted {{ background: #f0f2f5; color: var(--muted); border-color: var(--line); }}

    .inline-actions {{
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
      margin-bottom: 10px;
    }}

    .ghost-btn {{
      border: 1px solid var(--border-default);
      border-radius: 6px;
      background: transparent;
      color: var(--text-secondary);
      cursor: pointer;
      font-size: 12px;
      font-weight: 600;
      padding: 6px 10px;
      transition: all var(--transition-fast);
    }}

    .ghost-btn:hover {{
      color: var(--text-primary);
      background: var(--surface-4);
      border-color: var(--border-strong);
    }}

    .small-note {{
      margin: 0;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.5;
    }}

    .mono {{
      font-family: "Menlo", "Monaco", "Courier New", monospace;
      font-size: 12px;
    }}

    .section-title {{
      margin: 24px 0 12px;
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 0.6px;
      text-transform: uppercase;
      color: var(--brand);
    }}

    .jump-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 8px;
      margin-top: 12px;
    }}

    .jump-btn {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      color: var(--ink);
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      padding: 10px 12px;
      text-align: left;
      transition: all 0.2s ease;
    }}

    .jump-btn:hover {{
      background: var(--surface-3);
      border-color: var(--border-strong);
      color: var(--text-primary);
      box-shadow: var(--shadow-sm);
    }}

    .wizard-list {{
      display: grid;
      gap: 10px;
      margin-top: 10px;
    }}

    .wizard-step {{
      border: 1px solid var(--line);
      border-radius: var(--radius-md);
      background: var(--surface-3);
      padding: 12px;
      line-height: 1.6;
    }}

    .wizard-step strong {{
      color: var(--ink);
      font-weight: 600;
    }}

    .wizard-actions {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 10px;
    }}

    .mode-switch {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 12px;
      margin-bottom: 8px;
    }}

    .mode-btn {{
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      background: transparent;
      color: var(--text-secondary);
      cursor: pointer;
      font-size: 13px;
      font-weight: 600;
      letter-spacing: 0.3px;
      padding: 8px 14px;
      transition: all var(--transition-fast);
    }}

    .mode-btn:hover {{
      border-color: var(--border-strong);
      background: rgba(24, 95, 165, 0.12);
      color: var(--text-primary);
    }}

    .mode-btn.active {{
      background: var(--brand);
      color: #ffffff;
      border-color: var(--brand);
    }}

    .panel-toolbar-host {{
      display: flex;
      gap: 10px;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      margin: 8px 0 12px;
    }}

    .panel-toolbar-host .small-note {{ margin: 0; }}

    .panel[data-collapsed="true"] > :not(h3):not(.panel-toolbar-host) {{
      display: none;
    }}

    .orb-hidden {{
      display: none !important;
    }}

    /* Animated Office Scene */
    .office-scene {{
      background: radial-gradient(circle at 50% -20%, #182136, #0f1117 48%, #0b0f1a 100%);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 16px;
      overflow: hidden;
      position: relative;
    }}

    .office-header {{
      padding: 14px;
      background: linear-gradient(180deg, rgba(9, 17, 35, 0.92), rgba(9, 17, 35, 0.65));
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }}

    .office-skyline {{
      height: 78px;
      background: linear-gradient(180deg, #0a1020 0%, #10192f 100%);
      position: relative;
      overflow: hidden;
      border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    }}

    .office-skyline::before,
    .office-skyline::after {{
      content: "";
      position: absolute;
      bottom: 0;
      width: 120%;
      height: 54px;
      left: -10%;
      background-image:
        linear-gradient(to right, rgba(22, 31, 54, 0.9) 0 5%, transparent 5% 8%, rgba(15, 24, 43, 0.95) 8% 14%, transparent 14% 17%, rgba(28, 37, 60, 0.92) 17% 22%, transparent 22% 26%, rgba(20, 30, 49, 0.95) 26% 33%, transparent 33% 36%, rgba(18, 27, 47, 0.95) 36% 43%, transparent 43% 46%, rgba(24, 35, 57, 0.92) 46% 53%, transparent 53% 56%, rgba(20, 30, 50, 0.95) 56% 63%, transparent 63% 66%, rgba(17, 25, 44, 0.95) 66% 74%, transparent 74% 77%, rgba(23, 34, 55, 0.94) 77% 86%, transparent 86% 89%, rgba(18, 27, 45, 0.95) 89% 100%);
      opacity: 0.95;
    }}

    .office-floor {{
      background: linear-gradient(180deg, #101626 0%, #111520 38%, #0d1220 100%);
      min-height: 292px;
      padding: 18px 14px 56px;
      position: relative;
    }}

    .office-desks {{
      display: grid;
      grid-template-columns: repeat(6, minmax(120px, 1fr));
      gap: 12px;
      align-items: end;
    }}

    .office-desk {{
      position: relative;
      min-height: 190px;
      border-radius: 12px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      background: linear-gradient(180deg, rgba(20, 28, 44, 0.7), rgba(12, 18, 31, 0.92));
      padding: 12px 8px;
      display: flex;
      flex-direction: column;
      justify-content: flex-end;
      align-items: center;
      transition: transform 200ms ease, border-color 200ms ease;
    }}

    .office-desk:hover {{
      transform: translateY(-2px);
      border-color: rgba(255, 255, 255, 0.18);
    }}

    .desk-label {{
      margin-top: 8px;
      font-size: 12px;
      color: #9ca9c9;
      font-weight: 600;
      letter-spacing: 0.4px;
    }}

    .agent-character {{
      position: relative;
      width: 42px;
      height: 76px;
      animation: agent-idle 2.5s ease-in-out infinite;
      transform-origin: center bottom;
    }}

    .agent-head {{
      width: 30px;
      height: 30px;
      border-radius: 999px;
      margin: 0 auto;
      background: var(--agent-color, #378add);
      position: relative;
      border: 2px solid rgba(255,255,255,0.18);
    }}

    .agent-head::before,
    .agent-head::after {{
      content: "";
      position: absolute;
      top: 10px;
      width: 3px;
      height: 3px;
      border-radius: 999px;
      background: #ffffff;
    }}

    .agent-head::before {{ left: 8px; }}
    .agent-head::after {{ right: 8px; }}

    .agent-status-ring {{
      position: absolute;
      inset: -4px;
      border: 2px solid var(--agent-color, #378add);
      border-radius: 999px;
      opacity: 0.75;
      animation: status-pulse 2s infinite;
    }}

    .agent-body {{
      width: 28px;
      height: 28px;
      margin: 4px auto 0;
      border-radius: 8px;
      background: color-mix(in srgb, var(--agent-color, #378add) 65%, #0f1117);
      border: 1px solid rgba(255,255,255,0.14);
    }}

    .desk-surface {{
      width: 84%;
      height: 16px;
      border-radius: 6px;
      background: linear-gradient(180deg, #222b3f, #1a2234);
      border: 1px solid rgba(255,255,255,0.12);
      margin-top: 8px;
    }}

    .desk-monitor {{
      width: 74%;
      min-height: 56px;
      border-radius: 8px;
      background: #0a0e1a;
      border: 1px solid rgba(255,255,255,0.14);
      padding: 6px;
      color: #d4e4ff;
      font-size: 10px;
      line-height: 1.3;
      box-shadow: 0 0 20px color-mix(in srgb, var(--agent-color, #378add) 35%, transparent);
      animation: screen-flicker 3s infinite;
      overflow: hidden;
    }}

    .office-monitor-primary {{
      font-size: 10px;
      font-weight: 600;
      color: #f5f7ff;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}

    .office-monitor-secondary {{
      margin-top: 2px;
      font-size: 9px;
      color: #8ec5ff;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}

    .office-tags,
    .office-thumbs,
    .office-bars,
    .office-candles,
    .office-health-dots,
    .office-code-lines,
    .office-grid-calendar {{
      margin-top: 5px;
    }}

    .office-thumbs {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 3px;
    }}

    .office-thumbs span {{
      display: block;
      height: 12px;
      border-radius: 3px;
      background: linear-gradient(135deg, rgba(255,255,255,0.15), rgba(255,255,255,0.04));
      border: 1px solid rgba(255,255,255,0.08);
    }}

    .office-bars,
    .office-candles {{
      height: 18px;
      display: flex;
      align-items: end;
      gap: 3px;
    }}

    .office-bars span,
    .office-candles span {{
      flex: 1;
      display: block;
      border-radius: 2px 2px 0 0;
      background: linear-gradient(180deg, color-mix(in srgb, var(--agent-color, #378add) 85%, white 15%), color-mix(in srgb, var(--agent-color, #378add) 55%, #091120 45%));
      animation: screen-flicker 3s infinite;
    }}

    .office-candles span.down {{
      background: linear-gradient(180deg, #ef4444, #5d1620);
      height: 45% !important;
    }}

    .office-health-dots {{
      display: flex;
      gap: 4px;
    }}

    .office-health-dots span {{
      width: 7px;
      height: 7px;
      border-radius: 999px;
      background: #22c55e;
      box-shadow: 0 0 6px rgba(34,197,94,0.75);
      animation: status-pulse 2s infinite;
    }}

    .office-code-lines {{
      display: grid;
      gap: 3px;
    }}

    .office-code-lines span {{
      display: block;
      height: 3px;
      border-radius: 999px;
      background: linear-gradient(90deg, #7dd3fc, rgba(125, 211, 252, 0.2));
    }}

    .office-grid-calendar {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 3px;
    }}

    .office-grid-calendar span {{
      display: block;
      aspect-ratio: 1;
      border-radius: 2px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(255,255,255,0.04);
    }}

    .office-grid-calendar span.filled {{
      background: rgba(139, 92, 246, 0.65);
    }}

    .agent-bubble {{
      position: absolute;
      top: 10px;
      max-width: 150px;
      border-radius: 10px;
      border: 1px solid color-mix(in srgb, var(--agent-color, #378add) 80%, #ffffff 20%);
      background: rgba(7, 11, 20, 0.95);
      color: #f5f7ff;
      padding: 6px 8px;
      font-size: 11px;
      line-height: 1.35;
      opacity: 0;
      transform: scale(0.9);
      pointer-events: none;
      z-index: 3;
    }}

    .agent-bubble.show {{
      opacity: 1;
      transform: scale(1);
      animation: bubble-in 0.2s ease-out;
    }}

    .office-desk[data-state="working"] .agent-character {{ animation: agent-working 0.8s ease infinite; }}
    .office-desk[data-state="success"] .agent-character {{ animation: success-jump 0.5s ease; }}
    .office-desk[data-state="error"] {{ box-shadow: inset 0 0 0 2px rgba(239,68,68,0.4); }}
    .office-desk[data-state="sleeping"] .agent-character {{ opacity: 0.65; }}

    .state-pill {{
      margin-top: 4px;
      font-size: 10px;
      color: #8fa2ce;
      text-transform: uppercase;
      letter-spacing: 0.7px;
      font-weight: 700;
    }}

    .office-ticker {{
      border-top: 1px solid rgba(255,255,255,0.08);
      background: rgba(8, 13, 25, 0.94);
      padding: 10px 12px;
      font-size: 12px;
      color: #dde7ff;
      display: flex;
      gap: 14px;
      overflow: hidden;
      white-space: nowrap;
    }}

    .office-ticker-track {{
      display: inline-flex;
      gap: 18px;
      animation: ticker-slide 22s linear infinite;
    }}

    .office-ticker-item {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      opacity: 0.95;
    }}

    .office-dot {{
      width: 8px;
      height: 8px;
      border-radius: 999px;
      display: inline-block;
      background: var(--dot-color, #378add);
      box-shadow: 0 0 8px var(--dot-color, #378add);
    }}

    @keyframes ticker-slide {{
      0% {{ transform: translateX(0); }}
      100% {{ transform: translateX(-50%); }}
    }}

    @keyframes agent-idle {{
      0%,100% {{ transform: translateY(0); }}
      50% {{ transform: translateY(-4px); }}
    }}

    @keyframes agent-working {{
      0%,100% {{ transform: translateY(0) translateX(0); }}
      25% {{ transform: translateY(-1px) translateX(1px); }}
      75% {{ transform: translateY(-1px) translateX(-1px); }}
    }}

    @keyframes screen-flicker {{
      0%,96%,100% {{ opacity: 0.8; }}
      98% {{ opacity: 1; }}
    }}

    @keyframes bubble-in {{
      from {{ opacity: 0; transform: scale(0.9); }}
      to {{ opacity: 1; transform: scale(1); }}
    }}

    @keyframes success-jump {{
      0%,100% {{ transform: translateY(0); }}
      40% {{ transform: translateY(-12px); }}
    }}

    @keyframes status-pulse {{
      0%,100% {{ box-shadow: 0 0 0 0 currentColor; }}
      50% {{ box-shadow: 0 0 0 5px transparent; }}
    }}

    textarea.action-input {{
      resize: vertical;
      font-family: inherit;
    }}

    @media (max-width: 768px) {{
      .shell {{
        padding: 16px 16px 90px;
      }}

      .app-layout {{
        grid-template-columns: 1fr;
      }}

      .sidebar {{
        display: none;
      }}

      .content-shell {{
        padding-bottom: 96px;
      }}

      .mobile-nav {{
        display: grid;
      }}

      .topbar {{
        margin-bottom: 20px;
        gap: 16px;
      }}

      .hero {{
        padding: 24px;
      }}

      .hero h1 {{
        font-size: 24px;
      }}

      .grid {{
        grid-template-columns: 1fr;
      }}

      .mini-wrap {{
        grid-template-columns: 1fr;
      }}

      .nav {{
        gap: 2px;
      }}

      .nav a {{
        padding: 8px 12px;
        font-size: 13px;
      }}

      .stat-strip {{
        grid-template-columns: 1fr 1fr;
      }}

      .office-desks {{
        grid-template-columns: repeat(2, minmax(120px, 1fr));
      }}
    }}

    @media (max-width: 480px) {{
      .shell {{
        padding: 12px 12px 96px;
      }}

      .brand {{
        font-size: 20px;
      }}

      .topbar {{
        flex-direction: column;
        align-items: flex-start;
        gap: 12px;
        margin-bottom: 16px;
      }}

      .nav {{
        width: 100%;
        gap: 2px;
      }}

      .nav a {{
        flex: 1;
        min-width: 70px;
        padding: 8px;
        font-size: 12px;
        text-align: center;
      }}

      .topbar {{
        position: static;
      }}

      .hero {{
        padding: 16px;
      }}

      .hero h1 {{
        font-size: 20px;
      }}

      .hero p {{
        font-size: 13px;
      }}

      .stat-strip {{
        grid-template-columns: 1fr;
      }}

      .office-desks {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <div class="app-layout">
    <aside class="sidebar">
      <div class="sidebar-brand">
        <p class="wordmark">ORB</p>
        <div class="version">Command Platform v0.5</div>
      </div>

      <div class="sidebar-section">
        <div class="sidebar-label">Navigate</div>
        <a href="/" class="sidebar-link" data-nav-path="/">
          <span class="sidebar-link-main"><span class="sidebar-icon">◈</span><span>Home</span></span>
        </a>
        <a href="/dashboard" class="sidebar-link" data-nav-path="/dashboard">
          <span class="sidebar-link-main"><span class="sidebar-icon">⌘</span><span>Dashboard</span></span>
        </a>
        <a href="/docs" class="sidebar-link" data-nav-path="/docs">
          <span class="sidebar-link-main"><span class="sidebar-icon">◎</span><span>API Docs</span></span>
        </a>
        <a href="/health" class="sidebar-link" data-nav-path="/health">
          <span class="sidebar-link-main"><span class="sidebar-icon">●</span><span>Health</span></span>
        </a>
      </div>

      <div class="sidebar-section">
        <div class="sidebar-label">Agents</div>
        <a href="/dashboard#orb-provisioning-panel" class="sidebar-link"><span class="sidebar-link-main"><span class="sidebar-icon">R</span><span>Rex</span></span><span class="sidebar-status-dot live"></span></a>
        <a href="/dashboard#orb-aria-panel" class="sidebar-link"><span class="sidebar-link-main"><span class="sidebar-icon">A</span><span>Aria</span></span><span class="sidebar-status-dot live"></span></a>
        <a href="/dashboard#orb-nova-panel" class="sidebar-link"><span class="sidebar-link-main"><span class="sidebar-icon">N</span><span>Nova</span></span><span class="sidebar-status-dot live"></span></a>
        <a href="/dashboard#orb-orion-panel" class="sidebar-link"><span class="sidebar-link-main"><span class="sidebar-icon">O</span><span>Orion</span></span><span class="sidebar-status-dot live"></span></a>
        <a href="/dashboard#orb-visual-center" class="sidebar-link"><span class="sidebar-link-main"><span class="sidebar-icon">S</span><span>Sage</span></span><span class="sidebar-status-dot live"></span></a>
        <a href="/dashboard#orb-visual-center" class="sidebar-link"><span class="sidebar-link-main"><span class="sidebar-icon">T</span><span>Atlas</span></span><span class="sidebar-status-dot live"></span></a>
      </div>

      <div class="sidebar-footer">
        <div class="profile-card">
          <div class="profile-avatar">O</div>
          <div class="profile-meta">
            <strong>Owner</strong>
            <span>Local command tier</span>
          </div>
        </div>
        <div class="sidebar-label">Shortcut: Cmd+K</div>
      </div>
    </aside>

    <div class="content-shell">
      <main class="shell">
        <header class="topbar">
          <p class="brand">ORB Platform</p>
          <div class="topbar-actions">
            <nav class="nav">
              <a href="/">Home</a>
              <a href="/dashboard">Dashboard</a>
              <a href="/login">Login</a>
              <a href="/docs">API Docs</a>
              <a href="/health">Health</a>
            </nav>
            <button type="button" class="icon-btn" onclick="orbToggleNotifications()">Notifications<span id="orb-notif-badge" class="notif-badge orb-hidden">0</span></button>
            <button type="button" class="icon-btn" onclick="orbToggleCommandTray()">Command Tray</button>
          </div>
        </header>
        {body}
      </main>
    </div>
  </div>

  <nav class="mobile-nav">
    <a href="/" data-nav-path="/">Home</a>
    <a href="/dashboard#orb-provisioning-panel">Leads</a>
    <a href="/dashboard" data-nav-path="/dashboard">Agents</a>
    <a href="/dashboard#orb-dashboard-ops">Approve</a>
    <a href="/dashboard#orb-visual-center">Chat</a>
  </nav>
  <aside id="orb-notification-drawer" class="overlay-panel">
    <h4>Notifications</h4>
    <p class="small-note">Alerts, approvals, and improvement proposals.</p>
    <div id="orb-notification-list" class="overlay-list">
      <div class="overlay-item">No notifications loaded.</div>
    </div>
  </aside>

  <aside id="orb-command-tray" class="overlay-panel">
    <h4>Command Tray</h4>
    <p class="small-note">High-signal shortcuts and platform summary.</p>
    <div class="right-tray-grid">
      <div class="tray-tile"><strong>Mode</strong><div id="orb-tray-mode" class="small-note">Automatic routing</div></div>
      <div class="tray-tile"><strong>Approvals</strong><div id="orb-tray-approvals" class="small-note">0 pending</div></div>
      <div class="tray-tile"><strong>Improvements</strong><div id="orb-tray-improvements" class="small-note">0 proposed</div></div>
      <div class="tray-tile"><strong>Brain coverage</strong><div id="orb-tray-brains" class="small-note">No data loaded yet</div></div>
    </div>
  </aside>
  <script>
    (function () {{
      const path = window.location.pathname;
      document.querySelectorAll('[data-nav-path]').forEach((el) => {{
        const target = el.getAttribute('data-nav-path') || '';
        el.classList.toggle('active', target === path);
      }});
    }})();

    function orbToggleNotifications() {{
      const el = document.getElementById('orb-notification-drawer');
      const tray = document.getElementById('orb-command-tray');
      if (tray) tray.classList.remove('open');
      if (el) el.classList.toggle('open');
    }}

    function orbToggleCommandTray() {{
      const el = document.getElementById('orb-command-tray');
      const drawer = document.getElementById('orb-notification-drawer');
      if (drawer) drawer.classList.remove('open');
      if (el) el.classList.toggle('open');
    }}

    function orbScrollTo(sectionId) {{
      const el = document.getElementById(sectionId);
      if (el) {{
        el.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
        return;
      }}

      if (sectionId) {{
        window.location.href = `/dashboard#${{encodeURIComponent(sectionId)}}`;
      }}
    }}
  </script>
</body>
</html>
"""


def render_home() -> str:
    """Returns the beginner-friendly ORB homepage."""
    body = """
<section class="hero">
  <h1>Welcome to ORB — Your AI Team</h1>
  <p>ORB is a team of AI assistants that work 24/7 to help run your business. No complicated setup. Just simple smart help.</p>
</section>

<section class="grid">
  <article class="panel">
    <h3>🗣️ Aria — Your Daily Assistant</h3>
    <p>Reads your email and calendar. Sends you a briefing every morning about what's important today.</p>
    <p style="margin-top:12px; font-size:13px;"><strong>What it does:</strong> Schedules → Priorities → Reminders</p>
    <button type="button" class="action-btn" onclick="orbScrollTo('orb-aria-panel')" style="margin-top:8px; width:100%;">Go to Aria</button>
  </article>

  <article class="panel">
    <h3>📱 Nova — Content Creator</h3>
    <p>Writes social media posts and listings automatically. You review, then it posts.</p>
    <p style="margin-top:12px; font-size:13px;"><strong>What it does:</strong> Content → Schedule → Post</p>
    <button type="button" class="action-btn" onclick="orbScrollTo('orb-nova-panel')" style="margin-top:8px; width:100%;">Go to Nova</button>
  </article>

  <article class="panel">
    <h3>📈 Orion — Stock Trading Helper</h3>
    <p>Tests trading strategies safely with fake money. Alerts you to real opportunities.</p>
    <p style="margin-top:12px; font-size:13px;"><strong>What it does:</strong> Strategy → Test → Alert</p>
    <button type="button" class="action-btn" onclick="orbScrollTo('orb-orion-panel')" style="margin-top:8px; width:100%;">Go to Orion</button>
  </article>

  <article class="panel">
    <h3>💬 Rex — Sales Assistant</h3>
    <p>Handles customer messages automatically. Qualifies leads, schedules calls, closes deals.</p>
    <p style="margin-top:12px; font-size:13px;"><strong>What it does:</strong> Answer → Qualify → Schedule</p>
    <button type="button" class="action-btn" onclick="orbScrollTo('orb-provisioning-panel')" style="margin-top:8px; width:100%;">Go to Rex</button>
  </article>

  <article class="panel">
    <h3>👁️ Sage — Business Analytics</h3>
    <p>Watches your business 24/7. Alerts you to problems and opportunities automatically.</p>
    <p style="margin-top:12px; font-size:13px;"><strong>What it does:</strong> Monitor → Alert → Analyze</p>
    <p style="margin-top:8px; font-size:13px; color:#666d80;"><em>Sage works automatically in the background.</em></p>
  </article>

  <article class="panel">
    <h3>⚙️ How ORB Works</h3>
    <p><strong>You stay in control.</strong> Every action needs your approval first. Nothing happens without you clicking "Yes".</p>
    <p style="margin-top:12px; font-size:13px;">1. AI suggests something<br/>2. You review it<br/>3. You approve or reject<br/>4. It happens (or doesn't)</p>
  </article>
</section>

<section class="panel" style="margin-top:24px;">
  <h3>Getting Started — 3 Steps</h3>
  <div class="wizard-list" style="margin-top:16px;">
    <div class="wizard-step">
      <strong>Step 1: Add Your Phone &amp; Email</strong>
      <p style="margin:8px 0 0; color:#666d80;">Go to <code>Settings</code> and add your contact info so ORB can reach you.</p>
    </div>
    <div class="wizard-step">
      <strong>Step 2: Turn On One Agent</strong>
      <p style="margin:8px 0 0; color:#666d80;">Start with <strong>Aria</strong> (simplest). Click "Send Briefing Now" to test it.</p>
    </div>
    <div class="wizard-step">
      <strong>Step 3: Check Back Tomorrow</strong>
      <p style="margin:8px 0 0; color:#666d80;">Let it work for a day or two. See what it does. Then add more agents.</p>
    </div>
  </div>
  <div style="margin-top:16px;">
    <a href="/docs" style="color:var(--brand); font-weight:600; text-decoration:none;">📖 Read Full Getting Started Guide</a>
  </div>
</section>

<section class="panel" style="margin-top:20px; background:#f5f7fc;">
  <h3>Common Questions</h3>
  <div style="margin-top:12px;">
    <p><strong>Q: Is my data safe?</strong><br/>A: Yes. Your data stays in your own database. ORB never sees personal info.</p>
    <p style="margin-top:12px;"><strong>Q: Do I have to pay?</strong><br/>A: Only for services you use (Claude AI ~$1-10/day, SMS ~$0.01 each).</p>
    <p style="margin-top:12px;"><strong>Q: What if something goes wrong?</strong><br/>A: You approve everything first. Nothing happens without you.</p>
  </div>
</section>

<div style="margin-top:24px; text-align:center;">
  <button type="button" class="action-btn" style="padding:12px 24px; font-size:14px;" onclick="document.location='/dashboard'">Go to Dashboard →</button>
  <p class="footer" style="margin-top:16px;">Questions? <a href="../GETTING_STARTED.md" style="color:var(--brand);">Read the plain-English guide</a></p>
</div>
"""
    return _page("ORB Home", body)


def render_dashboard(data: dict[str, Any] | None = None) -> str:
    """Returns a command-center dashboard shell with live or fallback data."""
    data = data or {}

    active_agents = int(data.get("active_agents", 0))
    pending_approvals = int(data.get("pending_approvals", 0))
    daily_cost_dollars = float(data.get("daily_cost_dollars", 0.0))
    recent_activity = data.get("recent_activity", [])
    agents = data.get("agents", [])
    quick_actions = data.get("quick_actions", [])
    db_status = escape(str(data.get("db_status", "unknown")))

    recent_items = "".join(
        f"<li>{escape(str(item))}</li>" for item in recent_activity[:8]
    ) or "<li>No recent activity logged yet.</li>"

    quick_action_items = "".join(
        f"<li>{escape(str(item))}</li>" for item in quick_actions[:8]
    ) or "<li>No quick actions available.</li>"

    agent_rows = "".join(
        "<tr>"
        f"<td>{escape(str(agent.get('name', 'Unnamed agent')))}</td>"
        f"<td>{escape(str(agent.get('role', 'unknown')))}</td>"
        f"<td>{escape(str(agent.get('status', 'unknown')))}</td>"
        f"<td>{escape(str(agent.get('last_action', 'No recent action')))}</td>"
        "</tr>"
        for agent in agents[:12]
    )
    if not agent_rows:
        agent_rows = "<tr><td colspan=\"4\">No agents found yet.</td></tr>"

    body = f"""
<section class="hero">
  <h1>Command Center</h1>
  <p>Live shell backed by Supabase data where available.</p>
  <span class="badge">Database: {db_status}</span>
</section>

<section class="panel" id="orb-commander-first" style="margin-bottom:12px; border-color:#2f4f7b;">
  <h3>Commander First</h3>
  <p class="small-note">Start here each morning. Pull your executive briefing, then issue one command to orchestrate the team.</p>
  <div style="display:grid; gap:8px; margin-bottom:10px; grid-template-columns: 1fr 1fr auto auto; align-items:center;">
    <input id="orb-commander-owner-id" type="text" class="action-input" placeholder="Owner ID" />
    <input id="orb-commander-message" type="text" class="action-input" placeholder="Tell Commander what you need today" />
    <button type="button" class="action-btn" onclick="orbLoadCommanderBriefing()">Load Briefing</button>
    <button type="button" class="action-btn" onclick="orbSendCommanderMessage()">Send</button>
  </div>
  <div class="stat-strip" style="margin-top:8px;">
    <div class="stat-tile"><div class="label">Urgent Alerts</div><div class="value" id="orb-commander-urgent">-</div></div>
    <div class="stat-tile"><div class="label">Approvals</div><div class="value" id="orb-commander-approvals">-</div></div>
    <div class="stat-tile"><div class="label">Revenue At Risk</div><div class="value" id="orb-commander-revenue">-</div></div>
  </div>
  <pre id="orb-commander-output" style="white-space:pre-wrap; background:#0f1f33; color:#d9f0ff; border-radius:10px; padding:10px; margin:10px 0 0 0; min-height:96px; font-size:12px;">Commander briefing will appear here.</pre>
</section>

<section class="panel" id="orb-control-index" style="margin-bottom:12px;">
  <h3>Operations Index</h3>
  <p class="small-note">Jump to the exact control block you need. This keeps daily operations UI-first and organized.</p>
  <div class="mode-switch">
    <button type="button" id="orb-mode-owner" class="mode-btn" onclick="orbSetMode('owner')">Owner Mode</button>
    <button type="button" id="orb-mode-operator" class="mode-btn" onclick="orbSetMode('operator')">Operator Mode</button>
  </div>
  <p id="orb-mode-description" class="small-note">Owner Mode prioritizes daily actions and summaries.</p>
  <div class="jump-grid">
    <button type="button" class="jump-btn" data-mode="both" onclick="orbScrollTo('orb-setup-wizard')">Setup Wizard</button>
    <button type="button" class="jump-btn" data-mode="operator" onclick="orbScrollTo('orb-api-actions')">API Actions</button>
    <button type="button" class="jump-btn" data-mode="owner" onclick="orbScrollTo('orb-aria-panel')">Aria</button>
    <button type="button" class="jump-btn" data-mode="operator" onclick="orbScrollTo('orb-provisioning-panel')">Provisioning</button>
    <button type="button" class="jump-btn" data-mode="owner" onclick="orbScrollTo('orb-nova-panel')">Nova</button>
    <button type="button" class="jump-btn" data-mode="owner" onclick="orbScrollTo('orb-orion-panel')">Orion</button>
    <button type="button" class="jump-btn" data-mode="operator" onclick="orbScrollTo('orb-dashboard-ops')">Dashboard Ops</button>
    <button type="button" class="jump-btn" data-mode="operator" onclick="orbScrollTo('orb-integration-center')">Integration Control</button>
    <button type="button" class="jump-btn" data-mode="both" onclick="orbScrollTo('orb-visual-center')">Visual Command Center</button>
    <button type="button" class="jump-btn" onclick="orbRefreshVisualCenter()">Refresh Everything</button>
  </div>
</section>

<section class="panel" id="orb-setup-wizard" data-section-key="setup-wizard" data-mode="both" style="margin-bottom:12px;">
  <h3>Setup Wizard</h3>
  <p class="small-note">Guided checklist for local readiness. Server-provided blockers are combined with browser-saved completion progress.</p>
  <div class="wizard-actions">
    <button type="button" class="action-btn" onclick="orbLoadSetupChecklist()">Load Checklist</button>
    <button type="button" class="action-btn" onclick="orbRunFullPreflight()">Run Full Preflight</button>
    <button type="button" class="action-btn" onclick="orbRunSchemaReadiness()">Run Schema Readiness</button>
    <button type="button" class="action-btn" onclick="orbWizardCompleteNext()">Complete Next Step</button>
    <button type="button" class="action-btn" onclick="orbWizardReset()">Reset Wizard</button>
  </div>
  <div class="stat-strip" style="margin-top:10px;">
    <div class="stat-tile"><div class="label">Ready</div><div class="value" id="orb-setup-ready">-</div></div>
    <div class="stat-tile"><div class="label">Attention</div><div class="value" id="orb-setup-attention">-</div></div>
    <div class="stat-tile"><div class="label">Local Done</div><div class="value" id="orb-setup-done">-</div></div>
  </div>
  <div id="orb-setup-steps" class="wizard-list">
    <div class="wizard-step">Load Setup Checklist to populate.</div>
  </div>
</section>

<section class="grid">
  <article class="panel" id="orb-core-actions">
    <h3>Agent Status</h3>
    <p>Agents currently marked active.</p>
    <p class="kpi ok">{active_agents} Active</p>
  </article>
  <article class="panel" id="orb-agent-ops">
    <h3>Approval Queue</h3>
    <p>Trade approvals waiting for YES/NO/STOP replies.</p>
    <p class="kpi warn">{pending_approvals} Pending</p>
  </article>
  <article class="panel" id="orb-api-actions" data-section-key="api-actions" data-mode="operator">
    <h3>Daily Cost</h3>
    <p>Estimated spend from AI + messaging actions today.</p>
    <p class="kpi">${daily_cost_dollars:.2f}</p>
  </article>
</section>

<section class="grid">
  <article class="panel" id="orb-aria-panel" data-section-key="aria" data-mode="owner">
    <h3>API Actions</h3>
    <p style="margin-bottom:8px; color:#5f6c82;">Run lightweight integration checks directly from this page.</p>
    <div style="display:grid; gap:8px; margin-bottom:8px;">
      <button type="button" class="action-btn" onclick="orbRunDatabaseTest()">Run Database Test</button>
      <button type="button" class="action-btn" onclick="orbRunClaudeTest()">Run Claude Test (minimal cost)</button>
      <div style="display:grid; grid-template-columns: 1fr auto; gap:8px;">
        <input id="orb-sms-to" type="text" class="action-input" placeholder="SMS number e.g. +19783909619" />
        <button type="button" class="action-btn" onclick="orbRunSmsTest()">Run SMS Test</button>
      </div>

      <div style="display:grid; gap:8px; border:1px dashed #c9dced; border-radius:10px; padding:10px;">
        <p style="margin:0; color:#5f6c82; font-size:13px;">TradingView Simulation (local)</p>
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px;">
          <input id="orb-tv-secret" type="text" class="action-input" placeholder="TradingView secret" />
          <input id="orb-tv-agent-id" type="text" class="action-input" placeholder="Agent ID (required)" />
        </div>
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px;">
          <input id="orb-tv-owner-phone" type="text" class="action-input" placeholder="Owner phone e.g. +19783909619" />
          <button type="button" class="action-btn" onclick="orbRunTradingViewSimulation()">Run TradingView Simulation</button>
        </div>
      </div>
    </div>
    <pre id="orb-action-result" style="white-space:pre-wrap; background:#0f1f33; color:#d9f0ff; border-radius:10px; padding:10px; margin:0; min-height:88px; font-size:12px;">Action output will appear here.</pre>
  </article>

  <article class="panel">
    <h3>Aria — Executive Assistant</h3>
    <p style="margin-bottom:8px; color:#5f6c82;">Manage daily priorities and briefings.</p>
    <div style="display:grid; gap:8px; margin-bottom:8px;">
      <button type="button" class="action-btn" onclick="orbShowBriefingPreview()">Preview Briefing</button>
      <button type="button" class="action-btn" onclick="orbSendBriefingNow()">Send Briefing Now (7am)</button>
    </div>
    <div style="display:grid; gap:8px; border:1px dashed #c9dced; border-radius:10px; padding:10px;">
      <p style="margin:0; color:#5f6c82; font-size:13px;">Add Today's Task</p>
      <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px;">
        <input id="orb-task-title" type="text" class="action-input" placeholder="Task title" />
        <select id="orb-task-priority" class="action-input">
          <option value="normal">Normal</option>
          <option value="high">High</option>
          <option value="low">Low</option>
        </select>
      </div>
      <button type="button" class="action-btn" onclick="orbAddTask()" style="grid-column:1/span 2;">Add Task</button>
    </div>
    <p style="margin-top:8px; margin-bottom:0; font-size:12px; color:#5f6c82;">
      <button type="button" onclick="orbLoadTasks()" style="background:none; border:none; color:#185fa5; cursor:pointer; font-weight:600;">View All Tasks →</button>
    </p>
  </article>

  <article class="panel" id="orb-provisioning-panel" data-section-key="provisioning" data-mode="operator">
    <h3>Identity Provisioning</h3>
    <p style="margin-bottom:8px; color:#5f6c82;">Spin up a new agent identity with phone, email, and role.</p>
    <div style="display:grid; gap:8px; border:1px dashed #c9dced; border-radius:10px; padding:10px;">
      <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px;">
        <input id="orb-owner-id" type="text" class="action-input" placeholder="Owner UUID" />
        <input id="orb-owner-phone" type="text" class="action-input" placeholder="Owner phone (optional)" />
      </div>
      <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px;">
        <input id="orb-agent-name" type="text" class="action-input" placeholder="Agent name e.g. Rex" />
        <input id="orb-agent-role" type="text" class="action-input" placeholder="Role e.g. wholesale_sales" />
      </div>
      <button type="button" class="action-btn" onclick="orbProvisionAgent()">Provision Agent</button>
    </div>
    <p style="margin-top:8px; margin-bottom:0; font-size:12px; color:#5f6c82;">Local-first behavior: uses your configured Twilio number if buying a new number is not enabled yet.</p>
  </article>

  <article class="panel" id="orb-nova-panel" data-section-key="nova" data-mode="owner">
    <h3>Nova - Content Agent</h3>
    <p style="margin-bottom:8px; color:#5f6c82;">Generate draft content, then approve or reject from one place.</p>
    <div style="display:grid; gap:8px; border:1px dashed #c9dced; border-radius:10px; padding:10px;">
      <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px;">
        <input id="orb-nova-owner-id" type="text" class="action-input" placeholder="Owner UUID" />
        <input id="orb-nova-week-start" type="text" class="action-input" placeholder="Week start YYYY-MM-DD" />
      </div>
      <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:8px;">
        <button type="button" class="action-btn" onclick="orbNovaWeeklyCalendar()">Generate Weekly Calendar</button>
        <button type="button" class="action-btn" onclick="orbNovaDemoListing()">Generate Demo Listing Post</button>
        <button type="button" class="action-btn" onclick="orbNovaLoadContent()">Load Content Queue</button>
      </div>
      <div style="display:grid; grid-template-columns: 1fr auto auto; gap:8px;">
        <input id="orb-nova-content-id" type="text" class="action-input" placeholder="Content ID" />
        <button type="button" class="action-btn" onclick="orbNovaApproveContent()">Approve</button>
        <button type="button" class="action-btn" onclick="orbNovaRejectContent()">Reject</button>
      </div>
      <input id="orb-nova-reject-reason" type="text" class="action-input" placeholder="Reject reason (for Reject action)" />
    </div>
  </article>

  <article class="panel" id="orb-orion-panel" data-section-key="orion" data-mode="owner">
    <h3>Orion - Paper Trader</h3>
    <p style="margin-bottom:8px; color:#5f6c82;">Ingest strategy notes, scan symbols, and run paper trade tests.</p>
    <div style="display:grid; gap:8px; border:1px dashed #c9dced; border-radius:10px; padding:10px;">
      <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px;">
        <input id="orb-orion-agent-id" type="text" class="action-input" placeholder="Agent UUID" />
        <input id="orb-orion-symbols" type="text" class="action-input" placeholder="Symbols e.g. ES,NQ" />
      </div>
      <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px;">
        <input id="orb-orion-strategy-name" type="text" class="action-input" placeholder="Strategy name" />
        <input id="orb-orion-source" type="text" class="action-input" placeholder="Source trader (optional)" />
      </div>
      <textarea id="orb-orion-notes" class="action-input" placeholder="Strategy notes for ingest" style="min-height:72px;"></textarea>
      <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px;">
        <button type="button" class="action-btn" onclick="orbOrionIngest()">Ingest Strategy</button>
        <button type="button" class="action-btn" onclick="orbOrionScan()">Scan Market</button>
        <button type="button" class="action-btn" onclick="orbOrionPerformance()">Performance</button>
        <button type="button" class="action-btn" onclick="orbOrionSmokeRun()">Run Orion Smoke</button>
      </div>
      <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:8px;">
        <input id="orb-orion-entry" type="number" step="0.0001" class="action-input" placeholder="Entry" />
        <input id="orb-orion-stop" type="number" step="0.0001" class="action-input" placeholder="Stop" />
        <input id="orb-orion-target" type="number" step="0.0001" class="action-input" placeholder="Target" />
      </div>
      <div style="display:grid; grid-template-columns: 1fr auto; gap:8px;">
        <select id="orb-orion-direction" class="action-input">
          <option value="long">Long</option>
          <option value="short">Short</option>
        </select>
        <button type="button" class="action-btn" onclick="orbOrionPaperTradeTest()">Run Paper Trade Test</button>
      </div>
    </div>
  </article>

  <article class="panel" id="orb-dashboard-ops" data-section-key="dashboard-ops" data-mode="operator">
    <h3>Level 6 Dashboard API</h3>
    <p style="margin-bottom:8px; color:#5f6c82;">Load real dashboard data and run approval actions from the shell.</p>
    <div style="display:grid; gap:8px; border:1px dashed #c9dced; border-radius:10px; padding:10px;">
      <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:8px;">
        <button type="button" class="action-btn" onclick="orbLoadOverview()">Load Overview</button>
        <button type="button" class="action-btn" onclick="orbLoadPipeline()">Load Pipeline</button>
        <button type="button" class="action-btn" onclick="orbLoadApprovals()">Load Approvals</button>
      </div>
      <input id="orb-dashboard-token" type="text" class="action-input" placeholder="Bearer token for approve/reject (required for protected routes)" />
      <div style="display:grid; grid-template-columns: 1fr auto auto; gap:8px;">
        <input id="orb-approval-id" type="text" class="action-input" placeholder="Approval activity ID" />
        <button type="button" class="action-btn" onclick="orbApproveActivity()">Approve</button>
        <button type="button" class="action-btn" onclick="orbRejectActivity()">Reject</button>
      </div>
      <input id="orb-reject-reason" type="text" class="action-input" placeholder="Reject reason (only needed for Reject)" />
    </div>
  </article>

  <article class="panel" id="orb-integration-center" data-section-key="integrations" data-mode="operator">
    <h3>Integration Control Center</h3>
    <p style="margin-bottom:8px; color:#5f6c82;">Operate integrations from UI: readiness snapshot, masked credentials, and live checks.</p>
    <div style="display:grid; gap:8px; border:1px dashed #c9dced; border-radius:10px; padding:10px; margin-bottom:8px;">
      <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px;">
        <button type="button" class="action-btn" onclick="orbLoadIntegrationStatus()">Load Integration Status</button>
        <button type="button" class="action-btn" onclick="orbRunIntegrationChecks()">Run Live Checks</button>
      </div>
      <p class="small-note">Live checks currently include: Supabase, Anthropic, OpenAI, Twilio.</p>
    </div>
    <div class="table-wrap" style="margin-bottom:8px;">
      <table class="mini-table">
        <thead>
          <tr><th>Integration</th><th>Status</th><th>Configured</th><th>Masked Details</th></tr>
        </thead>
        <tbody id="orb-integration-rows">
          <tr><td colspan="4">Load Integration Status to populate.</td></tr>
        </tbody>
      </table>
    </div>
    <pre id="orb-integration-result" style="white-space:pre-wrap; background:#0f1f33; color:#d9f0ff; border-radius:10px; padding:10px; margin:0; min-height:88px; font-size:12px;">Integration check output will appear here.</pre>
  </article>

  <article class="panel" id="orb-quick-reference" data-section-key="quick-reference" data-mode="operator">
    <h3>Quick Actions Reference</h3>
    <ul class="list">{quick_action_items}</ul>
    <h3 style="margin-top:12px;">Tip</h3>
    <p style="margin-bottom:8px; color:#5f6c82;">Use <code>/dashboard/data</code> for machine-readable live metrics (for your future React frontend).</p>
  </article>
</section>

<section class="grid">
  <article class="panel" id="orb-recent-activity" data-section-key="recent-activity" data-mode="both">
    <h3>Recent Activity</h3>
    <ul class="list">{recent_items}</ul>
  </article>
</section>

<section class="panel" id="orb-ai-brains" data-section-key="ai-brains" data-mode="both" style="margin-top:12px;">
  <h3>Open AI Layer</h3>
  <p class="small-note">Connected brain providers, routing modes, and model coverage for current and future AI stacks.</p>
  <div class="mini-mode-row" id="orb-brain-modes">
    <span class="chip chip-muted">Loading routing modes...</span>
  </div>
  <div class="brain-card-grid" id="orb-brain-cards">
    <div class="brain-card">Loading AI brain inventory...</div>
  </div>
</section>

<section class="panel" id="orb-improvements-panel" data-section-key="improvements" data-mode="both" style="margin-top:12px;">
  <h3>Improvement Approval Center</h3>
  <p class="small-note">Nothing changes without approval. Review proposed behavior, prompt, routing, and cost optimizations here.</p>
  <div class="improvement-grid" id="orb-improvement-cards">
    <div class="improvement-card">Loading improvement proposals...</div>
  </div>
</section>

<section class="panel table-wrap" id="orb-live-agents" data-section-key="live-agents" data-mode="both" style="margin-top:12px;">
  <h3>Live Agent Cards</h3>
  <table class="agents-table">
    <thead>
      <tr>
        <th>Name</th>
        <th>Role</th>
        <th>Status</th>
        <th>Last Action</th>
      </tr>
    </thead>
    <tbody>{agent_rows}</tbody>
  </table>
</section>

<section class="panel" id="orb-visual-center" data-section-key="visual-center" data-mode="both" style="margin-top:12px;">
  <h3>Animated Office Command Center</h3>
  <p style="margin-bottom:10px; color:#5f6c82;">Live operations floor with six active agents, speech bubbles, and real-time activity feed.</p>
  <div class="inline-actions">
    <button type="button" class="action-btn" onclick="orbRefreshVisualCenter()">Refresh Visual Center</button>
    <span class="small-note">Last refresh: <span id="orb-last-refresh">not yet loaded</span></span>
  </div>

  <div class="office-scene">
    <div class="office-header">
      <div class="stat-strip" style="margin-bottom:0;">
        <div class="stat-tile"><div class="label">Leads Today</div><div class="value" id="orb-stat-leads">-</div></div>
        <div class="stat-tile"><div class="label">Calls Today</div><div class="value" id="orb-stat-calls">-</div></div>
        <div class="stat-tile"><div class="label">Tasks Done</div><div class="value" id="orb-stat-appts">-</div></div>
        <div class="stat-tile"><div class="label">Paper PnL</div><div class="value" id="orb-stat-pnl">-</div></div>
        <div class="stat-tile"><div class="label">AI Cost</div><div class="value" id="orb-stat-cost">-</div></div>
      </div>
    </div>

    <div class="office-skyline"></div>

    <div class="office-floor">
      <div class="office-desks">
        <div class="office-desk" id="orb-agent-rex" data-agent="rex" data-state="idle" style="--agent-color:#14b8a6;">
          <div class="agent-bubble" id="orb-bubble-rex">Ready.</div>
          <div class="agent-character"><div class="agent-head"><span class="agent-status-ring"></span></div><div class="agent-body"></div></div>
          <div class="desk-monitor" id="orb-monitor-rex">
            <div class="office-monitor-primary">Lead queue active</div>
            <div class="office-monitor-secondary">John Smith • HOT</div>
            <div class="office-tags"><span class="chip chip-hot">HOT</span><span class="chip chip-warm">WARM</span><span class="chip chip-cold">COLD</span></div>
            <div class="office-bars"><span style="height:40%"></span><span style="height:68%"></span><span style="height:55%"></span><span style="height:74%"></span></div>
          </div>
          <div class="desk-surface"></div>
          <div class="state-pill" id="orb-state-rex">IDLE</div>
          <div class="desk-label">Rex</div>
        </div>

        <div class="office-desk" id="orb-agent-aria" data-agent="aria" data-state="idle" style="--agent-color:#8b5cf6;">
          <div class="agent-bubble" id="orb-bubble-aria">Ready.</div>
          <div class="agent-character"><div class="agent-head"><span class="agent-status-ring"></span></div><div class="agent-body"></div></div>
          <div class="desk-monitor" id="orb-monitor-aria">
            <div class="office-monitor-primary">09:00 Strategy Sync</div>
            <div class="office-monitor-secondary">Inbox triage • 4 tasks</div>
            <div class="office-grid-calendar"><span></span><span class="filled"></span><span></span><span class="filled"></span><span></span><span></span><span class="filled"></span><span></span></div>
          </div>
          <div class="desk-surface"></div>
          <div class="state-pill" id="orb-state-aria">IDLE</div>
          <div class="desk-label">Aria</div>
        </div>

        <div class="office-desk" id="orb-agent-nova" data-agent="nova" data-state="idle" style="--agent-color:#ff6b6b;">
          <div class="agent-bubble" id="orb-bubble-nova">Ready.</div>
          <div class="agent-character"><div class="agent-head"><span class="agent-status-ring"></span></div><div class="agent-body"></div></div>
          <div class="desk-monitor" id="orb-monitor-nova">
            <div class="office-monitor-primary">Listing post in review</div>
            <div class="office-monitor-secondary">Queue: 3 scheduled</div>
            <div class="office-thumbs"><span></span><span></span><span></span></div>
          </div>
          <div class="desk-surface"></div>
          <div class="state-pill" id="orb-state-nova">IDLE</div>
          <div class="desk-label">Nova</div>
        </div>

        <div class="office-desk" id="orb-agent-orion" data-agent="orion" data-state="idle" style="--agent-color:#f59e0b;">
          <div class="agent-bubble" id="orb-bubble-orion">Ready.</div>
          <div class="agent-character"><div class="agent-head"><span class="agent-status-ring"></span></div><div class="agent-body"></div></div>
          <div class="desk-monitor" id="orb-monitor-orion">
            <div class="office-monitor-primary">PAPER ONLY</div>
            <div class="office-monitor-secondary">ES 87% confidence</div>
            <div class="office-candles"><span></span><span class="down"></span><span></span><span></span><span class="down"></span></div>
          </div>
          <div class="desk-surface"></div>
          <div class="state-pill" id="orb-state-orion">IDLE</div>
          <div class="desk-label">Orion</div>
        </div>

        <div class="office-desk" id="orb-agent-sage" data-agent="sage" data-state="idle" style="--agent-color:#3b82f6;">
          <div class="agent-bubble" id="orb-bubble-sage">Ready.</div>
          <div class="agent-character"><div class="agent-head"><span class="agent-status-ring"></span></div><div class="agent-body"></div></div>
          <div class="desk-monitor" id="orb-monitor-sage">
            <div class="office-monitor-primary">Uptime 99.8%</div>
            <div class="office-monitor-secondary">All health checks green</div>
            <div class="office-health-dots"><span></span><span></span><span></span><span></span></div>
          </div>
          <div class="desk-surface"></div>
          <div class="state-pill" id="orb-state-sage">IDLE</div>
          <div class="desk-label">Sage</div>
        </div>

        <div class="office-desk" id="orb-agent-atlas" data-agent="atlas" data-state="idle" style="--agent-color:#22c55e;">
          <div class="agent-bubble" id="orb-bubble-atlas">Ready.</div>
          <div class="agent-character"><div class="agent-head"><span class="agent-status-ring"></span></div><div class="agent-body"></div></div>
          <div class="desk-monitor" id="orb-monitor-atlas">
            <div class="office-monitor-primary">287 / 287 PASS</div>
            <div class="office-monitor-secondary">Security score 94/100</div>
            <div class="office-code-lines"><span></span><span></span><span></span></div>
          </div>
          <div class="desk-surface"></div>
          <div class="state-pill" id="orb-state-atlas">IDLE</div>
          <div class="desk-label">Atlas</div>
        </div>
      </div>
    </div>

    <div class="office-ticker">
      <div class="office-ticker-track" id="orb-office-ticker">
        <span class="office-ticker-item"><span class="office-dot" style="--dot-color:#22c55e;"></span>Waiting for live events...</span>
      </div>
    </div>
  </div>

  <div class="mini-wrap" style="margin-top:10px;">
    <div class="mini-panel">
      <p class="mini-title">Recent Activity</p>
      <table class="mini-table">
        <thead>
          <tr><th>Type</th><th>Description</th><th>Time</th></tr>
        </thead>
        <tbody id="orb-activity-rows">
          <tr><td colspan="3">Load Overview to populate.</td></tr>
        </tbody>
      </table>
    </div>

    <div class="mini-panel">
      <p class="mini-title">Pipeline Snapshot</p>
      <ul class="mini-list" id="orb-pipeline-list">
        <li>Load Pipeline to populate.</li>
      </ul>
    </div>
  </div>

  <div class="mini-panel" style="margin-top:10px;">
    <p class="mini-title">Approval Queue</p>
    <table class="mini-table">
      <thead>
          <tr><th>ID</th><th>Type</th><th>Description</th><th>Status</th><th>Quick</th></tr>
      </thead>
      <tbody id="orb-approvals-rows">
          <tr><td colspan="5">Load Approvals to populate.</td></tr>
      </tbody>
    </table>
  </div>

  <div class="mini-panel" style="margin-top:10px;">
    <p class="mini-title">Orion Performance Snapshot</p>
    <div id="orb-orion-summary" class="small-note">Enter Orion Agent UUID and click Refresh Visual Center.</div>
    <ul id="orb-orion-recommendations" class="mini-list" style="margin-top:8px;">
      <li>No recommendations loaded.</li>
    </ul>
  </div>

  <div class="mini-panel" style="margin-top:10px;">
    <p class="mini-title">Orion Smoke Runs</p>
    <div class="inline-actions" style="margin-bottom:6px;">
      <button type="button" class="ghost-btn" onclick="orbSmokeClearHistory()">Clear History</button>
    </div>
    <div id="orb-smoke-last" class="small-note">No smoke run recorded in this browser yet.</div>
    <ul id="orb-smoke-history" class="mini-list" style="margin-top:8px;">
      <li>No smoke history yet.</li>
    </ul>
  </div>
</section>

<script>
  const ORB_SMOKE_STORAGE_KEY = 'orbOrionSmokeHistoryV1';
  const ORB_SETUP_STORAGE_KEY = 'orbSetupWizardStateV1';
  const ORB_UI_PREFS_STORAGE_KEY = 'orbDashboardUiPrefsV1';
  const ORB_REMEMBERED_FIELDS = [
    'orb-owner-id',
    'orb-owner-phone',
    'orb-agent-name',
    'orb-agent-role',
    'orb-nova-owner-id',
    'orb-nova-week-start',
    'orb-orion-agent-id',
    'orb-orion-symbols',
    'orb-orion-strategy-name',
    'orb-orion-source',
    'orb-tv-agent-id',
    'orb-sms-to'
  ];

  function orbEscape(value) {{
    return String(value || '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#39;');
  }}

  const ORB_AGENT_COLORS = {{
    rex: '#14b8a6',
    aria: '#8b5cf6',
    nova: '#ff6b6b',
    orion: '#f59e0b',
    sage: '#3b82f6',
    atlas: '#22c55e',
  }};

  const ORB_AGENT_SAMPLE_LINES = {{
    rex: 'Calling John Smith...',
    aria: 'Summarizing your 9am meeting...',
    nova: 'Creating listing post for 123 Oak...',
    orion: 'ES setup detected - 87% confidence',
    sage: 'Platform health: 99.8% - all good',
    atlas: '287 tests passing - no issues',
  }};

  let orbOfficeSocket = null;
  let orbOfficeSeenKey = '';

  function orbResolveAgentKey(agentId, agentName, message) {{
    const source = `${{agentId || ''}} ${{agentName || ''}} ${{message || ''}}`.toLowerCase();
    if (source.includes('rex')) return 'rex';
    if (source.includes('aria')) return 'aria';
    if (source.includes('nova')) return 'nova';
    if (source.includes('orion')) return 'orion';
    if (source.includes('sage')) return 'sage';
    if (source.includes('atlas')) return 'atlas';
    return 'atlas';
  }}

  function orbOfficePushTicker(agentKey, text) {{
    const ticker = document.getElementById('orb-office-ticker');
    if (!ticker) return;
    const color = ORB_AGENT_COLORS[agentKey] || '#378add';
    const item = `<span class="office-ticker-item"><span class="office-dot" style="--dot-color:${{orbEscape(color)}}"></span>${{orbEscape(text)}}</span>`;
    const current = ticker.innerHTML || '';
    ticker.innerHTML = item + current;
    const all = Array.from(ticker.querySelectorAll('.office-ticker-item')).slice(0, 16);
    ticker.innerHTML = all.map((el) => el.outerHTML).join('');
  }}

  function orbActivateNav() {{
    const path = window.location.pathname;
    document.querySelectorAll('[data-nav-path]').forEach((el) => {{
      const target = el.getAttribute('data-nav-path') || '';
      const active = target === path;
      el.classList.toggle('active', active);
    }});
  }}

  function orbAnimateStatValue(elementId, nextValue, options) {{
    const el = document.getElementById(elementId);
    if (!el) return;

    const settings = options || {{}};
    const prefix = settings.prefix || '';
    const suffix = settings.suffix || '';
    const decimals = Number(settings.decimals || 0);
    const duration = Number(settings.duration || 600);
    const rawCurrent = Number(el.dataset.numericValue || 0);
    const target = Number(nextValue);

    if (!Number.isFinite(target)) {{
      el.textContent = prefix + '-' + suffix;
      return;
    }}

    const start = performance.now();
    function frame(now) {{
      const progress = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - progress, 3);
      const value = rawCurrent + (target - rawCurrent) * eased;
      el.textContent = prefix + value.toFixed(decimals) + suffix;
      if (progress < 1) {{
        requestAnimationFrame(frame);
      }} else {{
        el.dataset.numericValue = String(target);
        el.textContent = prefix + target.toFixed(decimals) + suffix;
      }}
    }}
    requestAnimationFrame(frame);
  }}

  function orbOfficeSetAgentState(agentKey, nextState, message) {{
    const desk = document.getElementById(`orb-agent-${{agentKey}}`);
    const bubble = document.getElementById(`orb-bubble-${{agentKey}}`);
    const monitor = document.getElementById(`orb-monitor-${{agentKey}}`);
    const state = document.getElementById(`orb-state-${{agentKey}}`);
    if (!desk || !bubble || !monitor || !state) return;

    desk.dataset.state = nextState;
    state.textContent = String(nextState || 'idle').toUpperCase();
    const primary = monitor.querySelector('.office-monitor-primary');
    const secondary = monitor.querySelector('.office-monitor-secondary');
    if (primary) {{
      primary.textContent = (message || ORB_AGENT_SAMPLE_LINES[agentKey] || 'Monitoring...').slice(0, 36);
    }} else {{
      monitor.textContent = (message || ORB_AGENT_SAMPLE_LINES[agentKey] || 'Monitoring...').slice(0, 64);
    }}
    if (secondary) {{
      secondary.textContent = `state: ${{String(nextState || 'idle').toUpperCase()}}`;
    }}

    if (message) {{
      bubble.textContent = String(message).slice(0, 60);
      bubble.classList.add('show');
      window.setTimeout(() => bubble.classList.remove('show'), 3000);
    }}
  }}

  function orbOfficeStateFromPayload(payload) {{
    const outcome = String((payload && payload.outcome) || '').toLowerCase();
    const actionType = String((payload && payload.action_type) || '').toLowerCase();
    const text = String((payload && payload.message) || '').toLowerCase();

    if (outcome.includes('error') || outcome.includes('fail') || text.includes('error')) return 'error';
    if (outcome.includes('success') || outcome.includes('ok')) return 'success';
    if (text.includes('calling') || actionType.includes('call')) return 'working';
    if (text.includes('sleep') || text.includes('paused')) return 'sleeping';
    if (text.includes('think') || actionType.includes('analy')) return 'thinking';
    return 'working';
  }}

  function orbOfficeApplyEvent(payload) {{
    const agentKey = orbResolveAgentKey(payload.agent_id, payload.agent_name, payload.message);
    const state = orbOfficeStateFromPayload(payload);
    const message = (payload.message || ORB_AGENT_SAMPLE_LINES[agentKey] || 'Working').slice(0, 60);
    orbOfficeSetAgentState(agentKey, state, message);
    orbOfficePushTicker(agentKey, `${{agentKey.toUpperCase()}}: ${{message}}`);
    window.setTimeout(() => orbOfficeSetAgentState(agentKey, 'idle', ''), 2400);
  }}

  function orbOfficeIngestOverviewRows(rows) {{
    if (!Array.isArray(rows) || !rows.length) return;
    const top = rows[0] || {{}};
    const key = `${{top.created_at || ''}}:${{top.description || ''}}:${{top.action_type || ''}}`;
    if (!key || key === orbOfficeSeenKey) return;
    orbOfficeSeenKey = key;
    orbOfficeApplyEvent({{
      agent_id: top.agent_id || '',
      agent_name: top.agent_name || '',
      action_type: top.action_type || 'event',
      message: top.description || 'Action complete',
      outcome: top.outcome || '',
    }});
  }}

  function orbConnectOfficeSocket() {{
    if (orbOfficeSocket) return;
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const endpoint = `${{protocol}}://${{window.location.host}}/ws/dashboard`;
    try {{
      orbOfficeSocket = new WebSocket(endpoint);
    }} catch (_err) {{
      return;
    }}

    orbOfficeSocket.onmessage = (event) => {{
      try {{
        const payload = JSON.parse(event.data || '{{}}');
        if (payload.type === 'agent_action') {{
          orbOfficeApplyEvent(payload);
        }}
      }} catch (_err) {{
        // Ignore malformed frames.
      }}
    }};

    orbOfficeSocket.onclose = () => {{
      orbOfficeSocket = null;
      window.setTimeout(orbConnectOfficeSocket, 2500);
    }};
  }}

  function orbSeedOffice() {{
    Object.entries(ORB_AGENT_SAMPLE_LINES).forEach(([key, line], idx) => {{
      window.setTimeout(() => orbOfficeSetAgentState(key, 'idle', line), 80 * idx);
    }});
  }}

  function orbReadTokenHeader() {{
    const tokenInput = document.getElementById('orb-dashboard-token');
    const raw = ((tokenInput && tokenInput.value) || '').trim();
    if (!raw) {{
      return {{}};
    }}
    return {{ Authorization: raw.startsWith('Bearer ') ? raw : `Bearer ${{raw}}` }};
  }}

  async function orbPostJson(url, payload) {{
    const response = await fetch(url, {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify(payload || {{}}),
    }});

    let data;
    try {{
      data = await response.json();
    }} catch (_err) {{
      data = {{ detail: 'No JSON response body.' }};
    }}

    return {{ ok: response.ok, status: response.status, data }};
  }}

  async function orbPostJsonWithAuth(url, payload) {{
    const headers = {{
      'Content-Type': 'application/json',
      ...orbReadTokenHeader(),
    }};

    const response = await fetch(url, {{
      method: 'POST',
      headers: headers,
      body: JSON.stringify(payload || {{}}),
    }});

    let data;
    try {{
      data = await response.json();
    }} catch (_err) {{
      data = {{ detail: 'No JSON response body.' }};
    }}

    return {{ ok: response.ok, status: response.status, data }};
  }}

  function orbCommanderOwnerId() {{
    const input = document.getElementById('orb-commander-owner-id');
    const ownerId = ((input && input.value) || '').trim();
    if (!ownerId) {{
      return null;
    }}
    try {{
      localStorage.setItem('orbOwnerId', ownerId);
    }} catch (_err) {{
      // Ignore storage issues.
    }}
    return ownerId;
  }}

  function orbCommanderShow(payload) {{
    const output = document.getElementById('orb-commander-output');
    if (!output) return;
    output.textContent = JSON.stringify(payload, null, 2);
  }}

  function orbCommanderRenderContext(contextPayload) {{
    const urgent = document.getElementById('orb-commander-urgent');
    const approvals = document.getElementById('orb-commander-approvals');
    const revenue = document.getElementById('orb-commander-revenue');
    const payload = contextPayload || {{}};
    const alerts = Array.isArray(payload.urgent_alerts) ? payload.urgent_alerts.length : 0;
    if (urgent) urgent.textContent = String(alerts);
    if (approvals) approvals.textContent = String(payload.pending_approvals || 0);
    if (revenue) revenue.textContent = String(payload.revenue_at_risk || 0);
  }}

  async function orbLoadCommanderBriefing() {{
    const ownerId = orbCommanderOwnerId();
    if (!ownerId) {{
      orbCommanderShow({{ detail: 'Enter Owner ID to load Commander briefing.' }});
      return;
    }}

    const headers = orbReadTokenHeader();
    try {{
      const briefingResp = await fetch(`/commander/briefing/${{encodeURIComponent(ownerId)}}`, {{ headers }});
      const briefingData = await briefingResp.json();
      if (!briefingResp.ok) {{
        orbCommanderShow(briefingData);
        return;
      }}
      orbCommanderShow(briefingData);

      const contextResp = await fetch(`/commander/context/${{encodeURIComponent(ownerId)}}`, {{ headers }});
      const contextData = await contextResp.json();
      if (contextResp.ok) {{
        orbCommanderRenderContext(contextData);
      }}
    }} catch (err) {{
      orbCommanderShow({{ error: err.message }});
    }}
  }}

  async function orbSendCommanderMessage() {{
    const ownerId = orbCommanderOwnerId();
    const input = document.getElementById('orb-commander-message');
    const message = ((input && input.value) || '').trim();
    if (!ownerId || !message) {{
      orbCommanderShow({{ detail: 'Owner ID and message are required.' }});
      return;
    }}

    const result = await orbPostJsonWithAuth('/commander/message', {{ owner_id: ownerId, message }});
    orbCommanderShow(result.data || {{}});
    orbShowResult('Commander Message', result);
    if (result.ok && input) {{
      input.value = '';
      orbLoadCommanderBriefing();
    }}
  }}

  function orbShowResult(title, result) {{
    const el = document.getElementById('orb-action-result');
    el.textContent = title + "\nStatus: " + result.status + "\n\n" + JSON.stringify(result.data, null, 2);
  }}

  function orbDefaultUiPrefs() {{
    return {{
      mode: 'owner',
      collapsed: {{}},
      fields: {{}},
    }};
  }}

  function orbReadUiPrefs() {{
    try {{
      const raw = localStorage.getItem(ORB_UI_PREFS_STORAGE_KEY);
      const parsed = raw ? JSON.parse(raw) : null;
      if (!parsed || typeof parsed !== 'object') {{
        return orbDefaultUiPrefs();
      }}
      return {{
        mode: parsed.mode === 'operator' ? 'operator' : 'owner',
        collapsed: parsed.collapsed && typeof parsed.collapsed === 'object' ? parsed.collapsed : {{}},
        fields: parsed.fields && typeof parsed.fields === 'object' ? parsed.fields : {{}},
      }};
    }} catch (_err) {{
      return orbDefaultUiPrefs();
    }}
  }}

  function orbWriteUiPrefs(nextPrefs) {{
    try {{
      localStorage.setItem(ORB_UI_PREFS_STORAGE_KEY, JSON.stringify({{
        mode: nextPrefs.mode === 'operator' ? 'operator' : 'owner',
        collapsed: nextPrefs.collapsed || {{}},
        fields: nextPrefs.fields || {{}},
      }}));
    }} catch (_err) {{
      // Ignore local storage failures.
    }}
  }}

  function orbPanelMatchesMode(panel, mode) {{
    const raw = String(panel.dataset.mode || 'both');
    const values = raw.split(',').map((item) => item.trim()).filter(Boolean);
    return values.includes('both') || values.includes(mode);
  }}

  function orbModeDescription(mode) {{
    if (mode === 'operator') {{
      return 'Operator Mode prioritizes setup, provisioning, integration checks, and control surfaces.';
    }}
    return 'Owner Mode prioritizes daily actions, agent workflows, and high-signal summaries.';
  }}

  function orbApplyUiPrefs() {{
    const prefs = orbReadUiPrefs();
    const mode = prefs.mode;
    const ownerBtn = document.getElementById('orb-mode-owner');
    const operatorBtn = document.getElementById('orb-mode-operator');
    const description = document.getElementById('orb-mode-description');

    if (ownerBtn) ownerBtn.classList.toggle('active', mode === 'owner');
    if (operatorBtn) operatorBtn.classList.toggle('active', mode === 'operator');
    if (description) description.textContent = orbModeDescription(mode);

    document.querySelectorAll('.panel[data-section-key]').forEach((panel) => {{
      const key = panel.dataset.sectionKey || '';
      const visible = orbPanelMatchesMode(panel, mode);
      panel.classList.toggle('orb-hidden', !visible);
      const collapsed = Boolean((prefs.collapsed || {{}})[key]);
      panel.setAttribute('data-collapsed', collapsed ? 'true' : 'false');

      const button = panel.querySelector('[data-role="collapse-toggle"]');
      if (button) {{
        button.textContent = collapsed ? 'Expand' : 'Collapse';
      }}
    }});

    document.querySelectorAll('.jump-btn[data-mode]').forEach((button) => {{
      const rule = String(button.dataset.mode || 'both').split(',').map((item) => item.trim());
      const visible = rule.includes('both') || rule.includes(mode);
      button.classList.toggle('orb-hidden', !visible);
    }});
  }}

  function orbSetMode(mode) {{
    const prefs = orbReadUiPrefs();
    prefs.mode = mode === 'operator' ? 'operator' : 'owner';
    orbWriteUiPrefs(prefs);
    orbApplyUiPrefs();
  }}

  function orbToggleSection(sectionKey) {{
    if (!sectionKey) return;
    const prefs = orbReadUiPrefs();
    prefs.collapsed[sectionKey] = !Boolean(prefs.collapsed[sectionKey]);
    orbWriteUiPrefs(prefs);
    orbApplyUiPrefs();
  }}

  function orbInstallPanelControls() {{
    document.querySelectorAll('.panel[data-section-key]').forEach((panel) => {{
      if (panel.querySelector('.panel-toolbar-host')) {{
        return;
      }}
      const title = panel.querySelector('h3');
      if (!title) {{
        return;
      }}
      const key = panel.dataset.sectionKey || '';
      const mode = String(panel.dataset.mode || 'both');
      const host = document.createElement('div');
      host.className = 'panel-toolbar-host';
      host.innerHTML = `
        <p class="small-note">View: <span class="mono">${{orbEscape(mode)}}</span> | Saved panel state persists in this browser.</p>
        <button type="button" class="ghost-btn" data-role="collapse-toggle">Collapse</button>
      `;
      const button = host.querySelector('[data-role="collapse-toggle"]');
      if (button) {{
        button.addEventListener('click', () => orbToggleSection(key));
      }}
      title.insertAdjacentElement('afterend', host);
    }});
  }}

  function orbRestoreRememberedFields() {{
    const prefs = orbReadUiPrefs();
    const fields = prefs.fields || {{}};
    ORB_REMEMBERED_FIELDS.forEach((fieldId) => {{
      const el = document.getElementById(fieldId);
      if (!el) return;
      if (typeof fields[fieldId] === 'string' && !el.value) {{
        el.value = fields[fieldId];
      }}
      el.addEventListener('change', () => orbPersistField(fieldId, el.value || ''));
      el.addEventListener('blur', () => orbPersistField(fieldId, el.value || ''));
    }});
  }}

  function orbPersistField(fieldId, value) {{
    const prefs = orbReadUiPrefs();
    prefs.fields[fieldId] = String(value || '');
    orbWriteUiPrefs(prefs);
  }}

  function orbSetupReadState() {{
    try {{
      const raw = localStorage.getItem(ORB_SETUP_STORAGE_KEY);
      const parsed = raw ? JSON.parse(raw) : {{ completed: [] }};
      if (!parsed || !Array.isArray(parsed.completed)) {{
        return {{ completed: [] }};
      }}
      return parsed;
    }} catch (_err) {{
      return {{ completed: [] }};
    }}
  }}

  function orbSetupWriteState(state) {{
    try {{
      localStorage.setItem(ORB_SETUP_STORAGE_KEY, JSON.stringify({{
        completed: Array.isArray(state && state.completed) ? state.completed : [],
      }}));
    }} catch (_err) {{
      // Ignore local storage failures.
    }}
  }}

  function orbRenderSetupChecklist(payload) {{
    const summary = (payload && payload.summary) || {{}};
    const steps = Array.isArray(payload && payload.steps) ? payload.steps : [];
    const state = orbSetupReadState();
    const completed = new Set(state.completed || []);

    const readyEl = document.getElementById('orb-setup-ready');
    const attentionEl = document.getElementById('orb-setup-attention');
    const doneEl = document.getElementById('orb-setup-done');
    const stepsEl = document.getElementById('orb-setup-steps');

    if (readyEl) readyEl.textContent = String(summary.ready ?? 0);
    if (attentionEl) attentionEl.textContent = String(summary.attention ?? 0);
    if (doneEl) doneEl.textContent = String((state.completed || []).length);
    if (!stepsEl) return;

    if (!steps.length) {{
      stepsEl.innerHTML = '<div class="wizard-step">No checklist steps available.</div>';
      return;
    }}

    const chipFor = (stepStatus, isDone) => {{
      if (isDone) return 'chip chip-ok';
      if (String(stepStatus || '').toLowerCase() === 'attention') return 'chip chip-pending';
      return 'chip chip-muted';
    }};

    const labelFor = (stepStatus, isDone) => {{
      if (isDone) return 'done';
      return String(stepStatus || 'unknown');
    }};

    stepsEl.innerHTML = steps.map((step) => {{
      const isDone = completed.has(step.id);
      return `
        <div class="wizard-step">
          <div style="display:flex; justify-content:space-between; gap:8px; align-items:flex-start; flex-wrap:wrap;">
            <strong>${{orbEscape(step.title || step.id || 'Step')}}</strong>
            <span class="${{chipFor(step.status, isDone)}}">${{orbEscape(labelFor(step.status, isDone))}}</span>
          </div>
          <p class="small-note" style="margin-top:6px;">${{orbEscape(step.detail || '')}}</p>
          <p class="small-note" style="margin-top:6px;"><strong>Next:</strong> ${{orbEscape(step.recommended_action || 'Review this step.')}}</p>
        </div>
      `;
    }}).join('');
  }}

  async function orbLoadSetupChecklist() {{
    try {{
      const resp = await fetch('/dashboard/setup-checklist');
      const data = await resp.json();
      orbRenderSetupChecklist(data);
      orbShowResult('Setup Checklist', {{ status: resp.status, data }});
    }} catch (err) {{
      orbShowResult('Setup Checklist', {{ status: 500, data: {{ error: err.message }} }});
    }}
  }}

  async function orbRunSchemaReadiness() {{
    try {{
      const resp = await fetch('/setup/schema-readiness');
      const data = await resp.json();
      orbShowResult('Schema Readiness', {{ status: resp.status, data }});
      if (resp.ok) {{
        await orbLoadSetupChecklist();
      }}
    }} catch (err) {{
      orbShowResult('Schema Readiness', {{ status: 500, data: {{ error: err.message }} }});
    }}
  }}

  async function orbRunFullPreflight() {{
    try {{
      const resp = await fetch('/setup/preflight');
      const data = await resp.json();
      orbShowResult('Platform Preflight', {{ status: resp.status, data }});
      if (resp.ok) {{
        await orbLoadSetupChecklist();
      }}
    }} catch (err) {{
      orbShowResult('Platform Preflight', {{ status: 500, data: {{ error: err.message }} }});
    }}
  }}

  function orbWizardCompleteNext() {{
    const stepsEl = document.getElementById('orb-setup-steps');
    if (!stepsEl) return;
    const cards = Array.from(stepsEl.children || []);
    const currentPayload = window.__orbSetupChecklistPayload || {{ steps: [] }};
    const steps = Array.isArray(currentPayload.steps) ? currentPayload.steps : [];
    const state = orbSetupReadState();
    const completed = new Set(state.completed || []);
    const next = steps.find((step) => !completed.has(step.id));
    if (!next) {{
      orbShowResult('Setup Wizard', {{ status: 200, data: {{ detail: 'All checklist steps are already marked done in this browser.' }} }});
      return;
    }}
    completed.add(next.id);
    orbSetupWriteState({{ completed: Array.from(completed) }});
    orbRenderSetupChecklist(currentPayload);
    orbShowResult('Setup Wizard', {{ status: 200, data: {{ detail: `Marked step '${{next.id}}' complete locally.` }} }});
  }}

  function orbWizardReset() {{
    orbSetupWriteState({{ completed: [] }});
    orbRenderSetupChecklist(window.__orbSetupChecklistPayload || {{ steps: [], summary: {{}} }});
    orbShowResult('Setup Wizard', {{ status: 200, data: {{ detail: 'Local setup wizard progress reset.' }} }});
  }}

  function orbScrollTo(sectionId) {{
    const el = document.getElementById(sectionId);
    if (el) {{
      el.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
    }}
  }}

  function orbSmokeReadHistory() {{
    try {{
      const raw = localStorage.getItem(ORB_SMOKE_STORAGE_KEY);
      const parsed = raw ? JSON.parse(raw) : [];
      if (!Array.isArray(parsed)) return [];
      return parsed.filter((item) => item && typeof item === 'object').slice(0, 6);
    }} catch (_err) {{
      return [];
    }}
  }}

  function orbSmokeWriteHistory(rows) {{
    try {{
      localStorage.setItem(ORB_SMOKE_STORAGE_KEY, JSON.stringify((rows || []).slice(0, 6)));
    }} catch (_err) {{
      // Ignore storage failures in private mode or restricted browsers.
    }}
  }}

  function orbSmokeRenderHistory() {{
    const lastEl = document.getElementById('orb-smoke-last');
    const historyEl = document.getElementById('orb-smoke-history');
    if (!lastEl || !historyEl) {{
      return;
    }}

    const rows = orbSmokeReadHistory();
    if (!rows.length) {{
      lastEl.textContent = 'No smoke run recorded in this browser yet.';
      historyEl.innerHTML = '<li>No smoke history yet.</li>';
      return;
    }}

    const latest = rows[0];
    const latestStatus = latest.ok ? 'Success' : 'Failed';
    const latestColor = latest.ok ? 'chip chip-ok' : 'chip chip-pending';
    lastEl.innerHTML = `
      <span class="${{latestColor}}">${{latestStatus}}</span>
      <span class="mono">${{orbEscape(latest.at || '')}}</span>
      | <strong>Scan:</strong> ${{orbEscape(latest.scan_status || '-')}}
      | <strong>Paper:</strong> ${{orbEscape(latest.paper_status || '-')}}
      | <strong>Setups:</strong> ${{orbEscape(latest.setup_count ?? '-')}}
    `;

    historyEl.innerHTML = rows.map((item) => `
      <li>
        <span class="mono">${{orbEscape(item.at || '')}}</span>
        - ${{item.ok ? 'ok' : 'err'}}
        - scan=${{orbEscape(item.scan_status || '-')}}
        - paper=${{orbEscape(item.paper_status || '-')}}
        - setups=${{orbEscape(item.setup_count ?? '-')}}
      </li>
    `).join('');
  }}

  function orbSmokeRecord(entry) {{
    const rows = orbSmokeReadHistory();
    rows.unshift(entry);
    orbSmokeWriteHistory(rows);
    orbSmokeRenderHistory();
  }}

  function orbSmokeClearHistory() {{
    const confirmed = window.confirm('Clear Orion smoke run history from this browser?');
    if (!confirmed) {{
      return;
    }}
    try {{
      localStorage.removeItem(ORB_SMOKE_STORAGE_KEY);
    }} catch (_err) {{
      // Ignore storage failures in private mode or restricted browsers.
    }}
    orbSmokeRenderHistory();
    orbShowResult('Orion Smoke History', {{
      status: 200,
      data: {{ detail: 'Smoke history cleared for this browser.' }},
    }});
  }}

  function orbRenderOverview(data) {{
    const stats = (data && data.stats) || {{}};
    document.getElementById('orb-last-refresh').textContent = new Date().toLocaleTimeString();
    orbAnimateStatValue('orb-stat-leads', Number(stats.leads_today ?? 0), {{ duration: 520 }});
    orbAnimateStatValue('orb-stat-calls', Number(stats.calls_made_today ?? 0), {{ duration: 560 }});
    orbAnimateStatValue('orb-stat-appts', Number(stats.appointments_booked ?? 0), {{ duration: 600 }});
    orbAnimateStatValue('orb-stat-pnl', Number(stats.paper_pnl_today ?? 0), {{ prefix: '$', decimals: 2, duration: 650 }});
    orbAnimateStatValue('orb-stat-cost', Number(stats.cost_today_dollars ?? 0), {{ prefix: '$', decimals: 2, duration: 700 }});

    const rows = Array.isArray(data && data.activity_feed) ? data.activity_feed.slice(0, 8) : [];
    orbOfficeIngestOverviewRows(rows);
    const tbody = document.getElementById('orb-activity-rows');
    if (!rows.length) {{
      tbody.innerHTML = '<tr><td colspan="3">No recent activity.</td></tr>';
      return;
    }}

    tbody.innerHTML = rows.map((row) => `
      <tr>
        <td class="mono">${{orbEscape(row.action_type || 'event')}}</td>
        <td>${{orbEscape(row.description || 'No description')}}</td>
        <td class="mono">${{orbEscape((row.created_at || '').slice(11, 16) || '--:--')}}</td>
      </tr>
    `).join('');
  }}

  function orbRenderPipeline(data) {{
    const pipeline = (data && data.pipeline) || {{}};
    const keys = ['new', 'contacted', 'qualified', 'appointment', 'offer', 'closed', 'other'];
    const list = document.getElementById('orb-pipeline-list');
    const chipClass = (key) => {{
      if (key === 'qualified' || key === 'offer') return 'chip chip-warm';
      if (key === 'closed') return 'chip chip-ok';
      if (key === 'new') return 'chip chip-cold';
      return 'chip chip-muted';
    }};
    const items = keys.map((key) => {{
      const rows = Array.isArray(pipeline[key]) ? pipeline[key] : [];
      return `<li><span class="${{chipClass(key)}}">${{orbEscape(key)}}</span> <strong>${{rows.length}}</strong></li>`;
    }});
    list.innerHTML = items.join('');
  }}

  function orbRenderApprovals(data) {{
    const approvals = Array.isArray(data && data.approvals) ? data.approvals.slice(0, 10) : [];
    const tbody = document.getElementById('orb-approvals-rows');
    if (!approvals.length) {{
      tbody.innerHTML = '<tr><td colspan="5">No pending approvals.</td></tr>';
      return;
    }}

    tbody.innerHTML = approvals.map((row) => `
      <tr>
        <td class="mono">${{orbEscape(row.id || '')}}</td>
        <td>${{orbEscape(row.action_type || 'event')}}</td>
        <td>${{orbEscape(row.description || 'No description')}}</td>
        <td>${{row.needs_approval ? '<span class="chip chip-pending">Pending</span>' : '<span class="chip chip-ok">Resolved</span>'}}</td>
        <td><button type="button" class="ghost-btn" onclick="orbUseApprovalId('${{orbEscape(row.id || '')}}')">Use ID</button></td>
      </tr>
    `).join('');
  }}

  function orbRenderOrionPerformance(data) {{
    const summaryEl = document.getElementById('orb-orion-summary');
    const recsEl = document.getElementById('orb-orion-recommendations');
    if (!summaryEl || !recsEl) {{
      return;
    }}

    const live = (data && data.live_trades) || {{}};
    const paper = (data && data.paper_trades) || {{}};
    const lookback = data && data.lookback_days;

    summaryEl.innerHTML = `
      <strong>Lookback:</strong> ${{orbEscape(lookback || 14)}} day(s)<br />
      <strong>Live Trades:</strong> ${{orbEscape(live.total_trades ?? 0)}} | <strong>Live Win Rate:</strong> ${{orbEscape(live.win_rate ?? 0)}}%<br />
      <strong>Paper Closed:</strong> ${{orbEscape(paper.closed_trades ?? 0)}} | <strong>Paper Win Rate:</strong> ${{orbEscape(paper.win_rate ?? 0)}}%
    `;

    const recommendations = Array.isArray(data && data.recommendations) ? data.recommendations : [];
    if (!recommendations.length) {{
      recsEl.innerHTML = '<li>No recommendations available.</li>';
      return;
    }}

    recsEl.innerHTML = recommendations.slice(0, 4).map((item) => `<li>${{orbEscape(item)}}</li>`).join('');
  }}

  async function orbLoadOrionSummary() {{
    const agentId = ((document.getElementById('orb-orion-agent-id') || {{}}).value || '').trim();
    const summaryEl = document.getElementById('orb-orion-summary');
    const recsEl = document.getElementById('orb-orion-recommendations');

    if (!agentId) {{
      if (summaryEl) {{
        summaryEl.textContent = 'Enter Orion Agent UUID and click Refresh Visual Center.';
      }}
      if (recsEl) {{
        recsEl.innerHTML = '<li>No recommendations loaded.</li>';
      }}
      return;
    }}

    try {{
      const resp = await fetch(`/agents/orion/performance?agent_id=${{encodeURIComponent(agentId)}}&days=14`);
      const data = await resp.json();
      if (resp.ok) {{
        orbRenderOrionPerformance(data);
      }} else if (summaryEl) {{
        summaryEl.textContent = `Unable to load Orion summary (status ${{resp.status}}).`;
      }}
    }} catch (err) {{
      if (summaryEl) {{
        summaryEl.textContent = `Unable to load Orion summary: ${{err.message}}`;
      }}
    }}
  }}

  function orbUseApprovalId(activityId) {{
    const input = document.getElementById('orb-approval-id');
    if (input) {{
      input.value = activityId || '';
    }}
  }}

  async function orbRunDatabaseTest() {{
    const result = await orbPostJson('/test/database', {{}});
    orbShowResult('Database Test', result);
  }}

  async function orbRunClaudeTest() {{
    const result = await orbPostJson('/test/claude', {{
      prompt: 'Reply with exactly: ok',
    }});
    orbShowResult('Claude Test', result);
  }}

  async function orbRunSmsTest() {{
    const input = document.getElementById('orb-sms-to');
    const to = ((input && input.value) || '').trim();
    if (!to) {{
      orbShowResult('SMS Test', {{
        status: 400,
        data: {{ detail: 'Please enter a destination number in E.164 format.' }},
      }});
      return;
    }}

    const result = await orbPostJson('/test/sms', {{
      to: to,
      message: 'ORB dashboard test message.',
    }});
    orbShowResult('SMS Test', result);
  }}

  async function orbRunTradingViewSimulation() {{
    const secretInput = document.getElementById('orb-tv-secret');
    const agentInput = document.getElementById('orb-tv-agent-id');
    const ownerPhoneInput = document.getElementById('orb-tv-owner-phone');

    const secret = ((secretInput && secretInput.value) || '').trim();
    const agentId = ((agentInput && agentInput.value) || '').trim();
    const ownerPhone = ((ownerPhoneInput && ownerPhoneInput.value) || '').trim();

    if (!secret || !agentId) {{
      orbShowResult('TradingView Simulation', {{
        status: 400,
        data: {{ detail: 'TradingView secret and agent ID are required.' }},
      }});
      return;
    }}

    const payload = {{
      symbol: 'ES',
      timeframe: '5',
      message: 'Momentum pullback setup with strong continuation and volume confirmation.',
      price: 5321.5,
      volume: 1000,
      direction: 'long',
      secret: secret,
      agent_id: agentId,
    }};

    if (ownerPhone) {{
      payload.owner_phone_number = ownerPhone;
    }}

    const result = await orbPostJson('/webhooks/tradingview', payload);
    orbShowResult('TradingView Simulation', result);
  }}

  // ─── Aria Functions ───────────────────────────────────────

  async function orbShowBriefingPreview() {{
    try {{
      const resp = await fetch('/aria/briefing/preview');
      const data = await resp.json();
      orbShowResult('Briefing Preview', {{
        status: resp.status,
        data: {{ briefing_text: data.briefing_text }},
      }});
    }} catch (err) {{
      orbShowResult('Briefing Preview', {{
        status: 500,
        data: {{ error: err.message }},
      }});
    }}
  }}

  async function orbSendBriefingNow() {{
    const result = await orbPostJson('/aria/briefing/send-now', {{}});
    orbShowResult('Briefing Sent', result);
  }}

  async function orbAddTask() {{
    const titleInput = document.getElementById('orb-task-title');
    const priorityInput = document.getElementById('orb-task-priority');
    
    const title = ((titleInput && titleInput.value) || '').trim();
    const priority = ((priorityInput && priorityInput.value) || 'normal').trim();
    
    if (!title) {{
      orbShowResult('Add Task', {{
        status: 400,
        data: {{ detail: 'Task title is required.' }},
      }});
      return;
    }}
    
    const result = await orbPostJson('/aria/tasks', {{
      title: title,
      priority: priority,
    }});
    
    orbShowResult('Task Added', result);
    
    // Clear the input
    if (titleInput) titleInput.value = '';
  }}

  async function orbLoadTasks() {{
    try {{
      const resp = await fetch('/aria/tasks/by-priority');
      const data = await resp.json();
      orbShowResult('All Tasks by Priority', {{
        status: resp.status,
        data: data,
      }});
    }} catch (err) {{
      orbShowResult('All Tasks', {{
        status: 500,
        data: {{ error: err.message }},
      }});
    }}
  }}

  async function orbProvisionAgent() {{
    const ownerId = ((document.getElementById('orb-owner-id') || {{}}).value || '').trim();
    const ownerPhone = ((document.getElementById('orb-owner-phone') || {{}}).value || '').trim();
    const agentName = ((document.getElementById('orb-agent-name') || {{}}).value || '').trim();
    const agentRole = ((document.getElementById('orb-agent-role') || {{}}).value || '').trim();

    if (!ownerId || !agentName || !agentRole) {{
      orbShowResult('Provision Agent', {{
        status: 400,
        data: {{ detail: 'Owner UUID, agent name, and role are required.' }},
      }});
      return;
    }}

    const payload = {{
      owner_id: ownerId,
      agent_name: agentName,
      role: agentRole,
      brain_provider: 'claude',
    }};

    if (ownerPhone) {{
      payload.owner_phone_number = ownerPhone;
    }}

    const result = await orbPostJson('/agents/provision', payload);
    orbShowResult('Provision Agent', result);
  }}

  // ─── Nova Functions ─────────────────────────────────────────

  function orbNovaReadCoreInputs() {{
    const ownerId = ((document.getElementById('orb-nova-owner-id') || {{}}).value || '').trim();
    const weekStart = ((document.getElementById('orb-nova-week-start') || {{}}).value || '').trim();
    return {{ ownerId, weekStart }};
  }}

  async function orbNovaWeeklyCalendar() {{
    const {{ ownerId, weekStart }} = orbNovaReadCoreInputs();
    if (!ownerId || !weekStart) {{
      orbShowResult('Nova Weekly Calendar', {{
        status: 400,
        data: {{ detail: 'Owner UUID and week start are required.' }},
      }});
      return;
    }}

    const result = await orbPostJson('/agents/nova/weekly-calendar', {{
      owner_id: ownerId,
      week_start: weekStart,
    }});
    orbShowResult('Nova Weekly Calendar', result);
  }}

  async function orbNovaDemoListing() {{
    const {{ ownerId }} = orbNovaReadCoreInputs();
    if (!ownerId) {{
      orbShowResult('Nova Demo Listing', {{
        status: 400,
        data: {{ detail: 'Owner UUID is required.' }},
      }});
      return;
    }}

    const result = await orbPostJson('/agents/nova/listing-post', {{
      owner_id: ownerId,
      property_data: {{
        address: '123 Main St',
        city: 'Houston',
        beds: 3,
        baths: 2,
        sqft: 1650,
        price: '$349,000',
        key_features: ['renovated kitchen', 'new roof', 'large backyard'],
      }},
      platforms: ['instagram', 'facebook', 'linkedin'],
    }});
    orbShowResult('Nova Demo Listing', result);
  }}

  async function orbNovaLoadContent() {{
    const {{ ownerId }} = orbNovaReadCoreInputs();
    if (!ownerId) {{
      orbShowResult('Nova Content Queue', {{
        status: 400,
        data: {{ detail: 'Owner UUID is required.' }},
      }});
      return;
    }}

    try {{
      const resp = await fetch(`/agents/nova/content?owner_id=${{encodeURIComponent(ownerId)}}`);
      const data = await resp.json();
      orbShowResult('Nova Content Queue', {{ status: resp.status, data }});
    }} catch (err) {{
      orbShowResult('Nova Content Queue', {{ status: 500, data: {{ error: err.message }} }});
    }}
  }}

  async function orbNovaApproveContent() {{
    const contentId = ((document.getElementById('orb-nova-content-id') || {{}}).value || '').trim();
    if (!contentId) {{
      orbShowResult('Nova Approve Content', {{
        status: 400,
        data: {{ detail: 'Content ID is required.' }},
      }});
      return;
    }}
    const result = await orbPostJson(`/agents/nova/content/${{contentId}}/approve`, {{}});
    orbShowResult('Nova Approve Content', result);
  }}

  async function orbNovaRejectContent() {{
    const contentId = ((document.getElementById('orb-nova-content-id') || {{}}).value || '').trim();
    const reason = ((document.getElementById('orb-nova-reject-reason') || {{}}).value || '').trim();
    if (!contentId || !reason) {{
      orbShowResult('Nova Reject Content', {{
        status: 400,
        data: {{ detail: 'Content ID and reject reason are required.' }},
      }});
      return;
    }}
    const result = await orbPostJson(`/agents/nova/content/${{contentId}}/reject`, {{ reason }});
    orbShowResult('Nova Reject Content', result);
  }}

  // ─── Orion Functions ────────────────────────────────────────

  function orbOrionReadCoreInputs() {{
    const agentId = ((document.getElementById('orb-orion-agent-id') || {{}}).value || '').trim();
    const symbolsRaw = ((document.getElementById('orb-orion-symbols') || {{}}).value || '').trim();
    const symbols = symbolsRaw
      ? symbolsRaw.split(',').map((item) => item.trim()).filter(Boolean)
      : ['ES', 'NQ'];
    return {{ agentId, symbols }};
  }}

  async function orbOrionIngest() {{
    const {{ agentId }} = orbOrionReadCoreInputs();
    const strategyName = ((document.getElementById('orb-orion-strategy-name') || {{}}).value || '').trim();
    const notes = ((document.getElementById('orb-orion-notes') || {{}}).value || '').trim();
    const sourceTrader = ((document.getElementById('orb-orion-source') || {{}}).value || '').trim();

    if (!agentId || !strategyName || notes.length < 10) {{
      orbShowResult('Orion Ingest', {{
        status: 400,
        data: {{ detail: 'Agent UUID, strategy name, and notes (10+ chars) are required.' }},
      }});
      return;
    }}

    const payload = {{
      agent_id: agentId,
      strategy_name: strategyName,
      notes: notes,
    }};
    if (sourceTrader) payload.source_trader = sourceTrader;

    const result = await orbPostJson('/agents/orion/ingest', payload);
    orbShowResult('Orion Ingest', result);
  }}

  async function orbOrionScan() {{
    const {{ agentId, symbols }} = orbOrionReadCoreInputs();
    if (!agentId) {{
      orbShowResult('Orion Scan', {{
        status: 400,
        data: {{ detail: 'Agent UUID is required.' }},
      }});
      return;
    }}

    const result = await orbPostJson('/agents/orion/scan', {{
      agent_id: agentId,
      symbols: symbols,
      timeframe: '5m',
    }});
    orbShowResult('Orion Scan', result);
  }}

  async function orbOrionPaperTradeTest() {{
    const {{ agentId, symbols }} = orbOrionReadCoreInputs();
    const entry = Number(((document.getElementById('orb-orion-entry') || {{}}).value || '').trim());
    const stop = Number(((document.getElementById('orb-orion-stop') || {{}}).value || '').trim());
    const target = Number(((document.getElementById('orb-orion-target') || {{}}).value || '').trim());
    const direction = ((document.getElementById('orb-orion-direction') || {{}}).value || 'long').trim();

    if (!agentId || !entry || !stop || !target) {{
      orbShowResult('Orion Paper Trade Test', {{
        status: 400,
        data: {{ detail: 'Agent UUID, entry, stop, and target are required.' }},
      }});
      return;
    }}

    const result = await orbPostJson('/agents/orion/paper-trade/test', {{
      agent_id: agentId,
      instrument: symbols[0] || 'ES',
      direction: direction,
      entry_price: entry,
      stop_loss: stop,
      take_profit: target,
      account_balance: 50000,
      risk_percent: 1.0,
    }});
    orbShowResult('Orion Paper Trade Test', result);
  }}

  async function orbOrionPerformance() {{
    const {{ agentId }} = orbOrionReadCoreInputs();
    if (!agentId) {{
      orbShowResult('Orion Performance', {{
        status: 400,
        data: {{ detail: 'Agent UUID is required.' }},
      }});
      return;
    }}

    try {{
      const resp = await fetch(`/agents/orion/performance?agent_id=${{encodeURIComponent(agentId)}}&days=14`);
      const data = await resp.json();
      if (resp.ok) {{
        orbRenderOrionPerformance(data);
      }}
      orbShowResult('Orion Performance', {{ status: resp.status, data }});
    }} catch (err) {{
      orbShowResult('Orion Performance', {{ status: 500, data: {{ error: err.message }} }});
    }}
  }}

  async function orbOrionSmokeRun() {{
    const {{ agentId, symbols }} = orbOrionReadCoreInputs();
    const strategyName = ((document.getElementById('orb-orion-strategy-name') || {{}}).value || '').trim();
    const sourceTrader = ((document.getElementById('orb-orion-source') || {{}}).value || '').trim();
    const notes = ((document.getElementById('orb-orion-notes') || {{}}).value || '').trim();

    const payload = {{
      symbols: symbols,
      timeframe: '5m',
      days: 14,
    }};
    if (agentId) payload.agent_id = agentId;
    if (strategyName) payload.strategy_name = strategyName;
    if (sourceTrader) payload.source_trader = sourceTrader;
    if (notes && notes.length >= 10) payload.notes = notes;

    const result = await orbPostJson('/agents/orion/smoke-run', payload);
    if (result.ok) {{
      orbRenderOrionPerformance({{
        lookback_days: 14,
        live_trades: result.data.live_trades,
        paper_trades: result.data.paper_trades,
        recommendations: result.data.recommendations,
      }});
      orbSmokeRecord({{
        at: new Date().toLocaleTimeString(),
        ok: true,
        scan_status: result.data.scan_status,
        paper_status: result.data.paper_status,
        setup_count: result.data.setup_count,
      }});
    }} else {{
      orbSmokeRecord({{
        at: new Date().toLocaleTimeString(),
        ok: false,
        scan_status: '-',
        paper_status: '-',
        setup_count: '-',
      }});
    }}
    orbShowResult('Orion Smoke Run', result);
  }}

  // ─── Level 6 Dashboard API Functions ─────────────────────────

  async function orbLoadOverview() {{
    try {{
      const resp = await fetch('/dashboard/overview');
      const data = await resp.json();
      orbRenderOverview(data);
      orbShowResult('Dashboard Overview', {{ status: resp.status, data }});
    }} catch (err) {{
      orbShowResult('Dashboard Overview', {{ status: 500, data: {{ error: err.message }} }});
    }}
  }}

  async function orbLoadCommandCenterBundle() {{
    try {{
      const resp = await fetch('/dashboard/command-center');
      const data = await resp.json();
      if (!resp.ok) {{
        orbShowResult('Command Center Bundle', {{ status: resp.status, data }});
        return false;
      }}

      orbRenderOverview(data.overview || {{}});
      orbRenderPipeline(data.pipeline || {{}});
      orbRenderApprovals(data.approvals || {{}});
      orbRenderIntegrations(data.integrations || {{}});
      orbRenderAiBrains(data.brains || {{}});
      orbRenderImprovements(data.improvements || {{}});
      orbRenderNotifications(data.notifications || {{}});
      const trayApprovals = document.getElementById('orb-tray-approvals');
      if (trayApprovals) {{
        trayApprovals.textContent = `${{(data.approvals && data.approvals.count) || 0}} pending`;
      }}
      window.__orbSetupChecklistPayload = data.setup || {{ steps: [], summary: {{}} }};
      orbRenderSetupChecklist(window.__orbSetupChecklistPayload);
      return true;
    }} catch (err) {{
      orbShowResult('Command Center Bundle', {{ status: 500, data: {{ error: err.message }} }});
      return false;
    }}
  }}

  async function orbLoadPipeline() {{
    try {{
      const resp = await fetch('/dashboard/pipeline');
      const data = await resp.json();
      orbRenderPipeline(data);
      orbShowResult('Dashboard Pipeline', {{ status: resp.status, data }});
    }} catch (err) {{
      orbShowResult('Dashboard Pipeline', {{ status: 500, data: {{ error: err.message }} }});
    }}
  }}

  async function orbLoadApprovals() {{
    try {{
      const resp = await fetch('/dashboard/approvals');
      const data = await resp.json();
      orbRenderApprovals(data);
      orbShowResult('Dashboard Approvals', {{ status: resp.status, data }});
    }} catch (err) {{
      orbShowResult('Dashboard Approvals', {{ status: 500, data: {{ error: err.message }} }});
    }}
  }}

  function orbIntegrationChipClass(status) {{
    const value = String(status || '').toLowerCase();
    if (value === 'ready') return 'chip chip-ok';
    if (value === 'warning') return 'chip chip-pending';
    return 'chip chip-muted';
  }}

  function orbRenderIntegrations(data) {{
    const rows = Array.isArray(data && data.integrations) ? data.integrations : [];
    const tbody = document.getElementById('orb-integration-rows');
    if (!tbody) return;
    if (!rows.length) {{
      tbody.innerHTML = '<tr><td colspan="4">No integration records available.</td></tr>';
      return;
    }}

    tbody.innerHTML = rows.map((row) => {{
      const details = row && row.details ? JSON.stringify(row.details) : '{{}}';
      return `
        <tr>
          <td>${{orbEscape(row.key || '')}}</td>
          <td><span class="${{orbIntegrationChipClass(row.status)}}">${{orbEscape(row.status || 'unknown')}}</span></td>
          <td>${{row.configured ? 'yes' : 'no'}}</td>
          <td class="mono">${{orbEscape(details)}}</td>
        </tr>
      `;
    }}).join('');
  }}

  function orbShowIntegrationResult(title, payload) {{
    const el = document.getElementById('orb-integration-result');
    if (!el) return;
    el.textContent = title + "\n\n" + JSON.stringify(payload, null, 2);
  }}

  async function orbLoadIntegrationStatus() {{
    try {{
      const resp = await fetch('/dashboard/integrations');
      const data = await resp.json();
      orbRenderIntegrations(data);
      orbShowIntegrationResult('Integration Status Snapshot', data);
    }} catch (err) {{
      orbShowIntegrationResult('Integration Status Snapshot', {{ error: err.message }});
    }}
  }}

  function orbRenderNotifications(data) {{
    const rows = Array.isArray(data && data.notifications) ? data.notifications : [];
    const list = document.getElementById('orb-notification-list');
    const badge = document.getElementById('orb-notif-badge');
    const unread = Number((data && data.unread_count) || rows.length || 0);

    if (badge) {{
      badge.textContent = String(unread);
      badge.classList.toggle('orb-hidden', unread < 1);
    }}

    if (!list) return;
    if (!rows.length) {{
      list.innerHTML = '<div class="overlay-item">No notifications right now.</div>';
      return;
    }}

    list.innerHTML = rows.map((row) => `
      <div class="overlay-item">
        <strong>${{orbEscape(row.title || 'Notification')}}</strong>
        <div class="small-note">${{orbEscape(row.message || '')}}</div>
      </div>
    `).join('');
  }}

  function orbRenderAiBrains(data) {{
    const rows = Array.isArray(data && data.brains) ? data.brains : [];
    const routing = (data && data.routing_modes) || {{}};
    const cards = document.getElementById('orb-brain-cards');
    const modes = document.getElementById('orb-brain-modes');
    const trayMode = document.getElementById('orb-tray-mode');
    const trayBrains = document.getElementById('orb-tray-brains');

    if (modes) {{
      const chips = [
        ['Automatic', !!routing.automatic],
        ['Budget', !!routing.budget_mode],
        ['Quality', !!routing.quality_mode],
        ['Privacy', !!routing.privacy_mode],
      ];
      modes.innerHTML = chips.map(([label, on]) => `<span class="chip ${{on ? 'chip-ok' : 'chip-muted'}}">${{label}}</span>`).join('');
    }}

    if (trayMode) {{
      trayMode.textContent = routing.privacy_mode ? 'Privacy mode' : routing.quality_mode ? 'Quality mode' : routing.budget_mode ? 'Budget mode' : 'Automatic routing';
    }}

    if (trayBrains) {{
      const connected = rows.filter((row) => row.connected).length;
      trayBrains.textContent = `${{connected}} / ${{rows.length}} providers connected`;
    }}

    if (!cards) return;
    if (!rows.length) {{
      cards.innerHTML = '<div class="brain-card">No AI brain inventory available.</div>';
      return;
    }}

    cards.innerHTML = rows.map((row) => `
      <article class="brain-card">
        <h4>${{orbEscape(row.label || row.key || 'Brain')}}</h4>
        <div><span class="chip ${{row.connected ? 'chip-ok' : 'chip-pending'}}">${{row.connected ? 'Connected' : 'Not connected'}}</span></div>
        <p class="small-note" style="margin-top:8px;">${{orbEscape(row.best_for || '')}}</p>
        <div class="metric-delta">${{orbEscape(row.cost_range || '')}}</div>
        <div class="brain-models">
          ${{(Array.isArray(row.models) ? row.models : []).slice(0, 4).map((model) => `<span class="chip chip-muted">${{orbEscape(model)}}</span>`).join('')}}
        </div>
      </article>
    `).join('');
  }}

  function orbRenderImprovements(data) {{
    const rows = Array.isArray(data && data.improvements) ? data.improvements : [];
    const cards = document.getElementById('orb-improvement-cards');
    const tray = document.getElementById('orb-tray-improvements');
    const proposed = rows.filter((row) => String(row.status || '') === 'proposed');

    if (tray) {{
      tray.textContent = `${{proposed.length}} proposed`;
    }}

    if (!cards) return;
    if (!rows.length) {{
      cards.innerHTML = '<div class="improvement-card">No improvement proposals available.</div>';
      return;
    }}

    cards.innerHTML = rows.map((row) => `
      <article class="improvement-card">
        <h4>${{orbEscape(String(row.agent_id || 'agent').toUpperCase())}} · ${{orbEscape(row.improvement_type || 'improvement')}}</h4>
        <div><span class="chip ${{String(row.status || '') === 'approved' ? 'chip-ok' : String(row.status || '') === 'rejected' ? 'chip-hot' : 'chip-pending'}}">${{orbEscape(row.status || 'unknown')}}</span></div>
        <p class="small-note" style="margin-top:8px;">${{orbEscape(row.description || '')}}</p>
        <div class="metric-delta">${{orbEscape(row.metric_name || 'metric')}}: ${{orbEscape(row.before_metric ?? '-')}} → ${{orbEscape(row.after_metric ?? '-')}}</div>
        <div class="wizard-actions" style="margin-top:10px;">
          <button type="button" class="action-btn" onclick="orbApproveImprovement('${{orbEscape(row.id || '')}}')">Approve</button>
          <button type="button" class="ghost-btn" onclick="orbRejectImprovement('${{orbEscape(row.id || '')}}')">Reject</button>
        </div>
      </article>
    `).join('');
  }}

  async function orbLoadNotifications() {{
    try {{
      const resp = await fetch('/dashboard/notifications');
      const data = await resp.json();
      orbRenderNotifications(data);
    }} catch (_err) {{
      orbRenderNotifications({{ notifications: [] }});
    }}
  }}

  async function orbLoadAiBrains() {{
    try {{
      const resp = await fetch('/dashboard/ai-brains');
      const data = await resp.json();
      orbRenderAiBrains(data);
    }} catch (_err) {{
      orbRenderAiBrains({{ brains: [], routing_modes: {{}} }});
    }}
  }}

  async function orbLoadImprovements() {{
    try {{
      const resp = await fetch('/dashboard/improvements');
      const data = await resp.json();
      orbRenderImprovements(data);
    }} catch (_err) {{
      orbRenderImprovements({{ improvements: [] }});
    }}
  }}

  async function orbApproveImprovement(improvementId) {{
    const result = await orbPostJsonWithAuth(`/dashboard/improvements/${{encodeURIComponent(improvementId)}}/approve`, {{}});
    orbShowResult('Improve Approve', result);
    if (result.ok) {{
      orbLoadImprovements();
      orbLoadNotifications();
    }}
  }}

  async function orbRejectImprovement(improvementId) {{
    const reason = window.prompt('Why are you rejecting this change?', 'Not now');
    if (!reason) return;
    const result = await orbPostJsonWithAuth(`/dashboard/improvements/${{encodeURIComponent(improvementId)}}/reject`, {{ reason }});
    orbShowResult('Improve Reject', result);
    if (result.ok) {{
      orbLoadImprovements();
      orbLoadNotifications();
    }}
  }}

  async function orbRunIntegrationChecks() {{
    const result = await orbPostJson('/dashboard/integrations/live-check', {{
      checks: ['supabase', 'anthropic', 'openai', 'twilio'],
    }});
    orbShowIntegrationResult('Integration Live Checks', {{
      status: result.status,
      data: result.data,
    }});
    await orbLoadIntegrationStatus();
  }}

  async function orbApproveActivity() {{
    const approvalInput = document.getElementById('orb-approval-id');
    const activityId = ((approvalInput && approvalInput.value) || '').trim();
    if (!activityId) {{
      orbShowResult('Approve Activity', {{
        status: 400,
        data: {{ detail: 'Approval activity ID is required.' }},
      }});
      return;
    }}

    const result = await orbPostJsonWithAuth(`/dashboard/approve/${{activityId}}`, {{}});
    orbShowResult('Approve Activity', result);
    if (result.ok) {{
      orbLoadApprovals();
    }}
  }}

  async function orbRejectActivity() {{
    const approvalInput = document.getElementById('orb-approval-id');
    const reasonInput = document.getElementById('orb-reject-reason');
    const activityId = ((approvalInput && approvalInput.value) || '').trim();
    const reason = ((reasonInput && reasonInput.value) || '').trim();

    if (!activityId) {{
      orbShowResult('Reject Activity', {{
        status: 400,
        data: {{ detail: 'Approval activity ID is required.' }},
      }});
      return;
    }}

    if (!reason) {{
      orbShowResult('Reject Activity', {{
        status: 400,
        data: {{ detail: 'Reject reason is required.' }},
      }});
      return;
    }}

    const result = await orbPostJsonWithAuth(`/dashboard/reject/${{activityId}}`, {{ reason }});
    orbShowResult('Reject Activity', result);
    if (result.ok) {{
      orbLoadApprovals();
    }}
  }}

  async function orbRefreshVisualCenter() {{
    await Promise.all([
      orbLoadCommandCenterBundle(),
      orbLoadOrionSummary(),
      orbLoadNotifications(),
      orbLoadAiBrains(),
      orbLoadImprovements(),
    ]);
    await orbLoadCommanderBriefing();
  }}

  // Load dashboard visuals automatically on first paint.
  window.addEventListener('DOMContentLoaded', () => {{
    const ownerInput = document.getElementById('orb-commander-owner-id');
    if (ownerInput) {{
      let ownerIdFromUrl = '';
      try {{
        ownerIdFromUrl = new URLSearchParams(window.location.search).get('owner_id') || '';
      }} catch (_err) {{
        ownerIdFromUrl = '';
      }}
      try {{
        ownerInput.value = ownerIdFromUrl || localStorage.getItem('orbOwnerId') || '';
        if (ownerInput.value) {{
          localStorage.setItem('orbOwnerId', ownerInput.value);
        }}
      }} catch (_err) {{
        ownerInput.value = ownerIdFromUrl || '';
      }}
    }}
    orbActivateNav();
    orbInstallPanelControls();
    orbRestoreRememberedFields();
    orbApplyUiPrefs();
    orbSmokeRenderHistory();
    orbSeedOffice();
    orbConnectOfficeSocket();
    orbRefreshVisualCenter();
  }});
</script>
"""
    return _page("ORB Dashboard", body)


def render_login() -> str:
    """Returns a simple login placeholder page."""
    body = """
<section class="hero">
  <h1>Login Placeholder</h1>
  <p>This page will be replaced by Supabase Auth (Level 9). For now, API auth uses JWT bearer tokens on protected routes.</p>
</section>

<section class="panel">
  <h3>Next Auth Milestone</h3>
  <p>Implement register/login/refresh endpoints and session UI for multi-tenant customers.</p>
</section>
"""
    return _page("ORB Login", body)


def render_admin_dashboard(summary: dict[str, Any] | None = None) -> str:
    """Returns a dedicated superadmin control shell."""
    context = summary or {}
    owner_email = escape(str(context.get("owner_email") or "superadmin"))
    role = escape(str(context.get("role") or "superadmin").upper())

    body = f"""
<section class="hero">
  <div style="display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap;">
    <div>
      <h1>ORB Admin Control Center</h1>
      <p>Platform-wide operations, customer management, and launch controls.</p>
    </div>
    <span style="display:inline-block; padding:6px 10px; border-radius:999px; background:#1f2937; color:#f9fafb; font-size:12px; letter-spacing:.04em;">ADMIN</span>
  </div>
</section>

<section class="panel" style="display:grid; gap:12px;">
  <h3>Session Context</h3>
  <p style="margin:0; color:#94a3b8;">Signed in as <strong>{owner_email}</strong> · Access tier: <strong>{role}</strong></p>
</section>

<section class="panel" style="display:grid; gap:10px;">
  <h3>Quick Actions</h3>
  <div class="actions" style="display:flex; flex-wrap:wrap; gap:10px;">
    <a class="action-btn" href="/admin/users">View users</a>
    <a class="action-btn" href="/admin/platform/health">Platform health</a>
    <a class="action-btn" href="/admin/feature-flags">Feature flags</a>
    <a class="action-btn" href="/dashboard">Back to user dashboard</a>
  </div>
</section>

<section class="panel" style="display:grid; gap:8px;">
  <h3>What This Controls</h3>
  <ul style="margin:0; padding-left:18px; color:#cbd5e1; line-height:1.6;">
    <li>User plan overrides and support interventions</li>
    <li>Feature flags with real-time rollout control</li>
    <li>Platform health checks and launch readiness visibility</li>
    <li>Audit-safe superadmin-only access operations</li>
  </ul>
</section>
"""
    return _page("ORB Admin", body)
