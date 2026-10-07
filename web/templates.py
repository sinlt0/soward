import config

BASE_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg: #08080b;
  --surface: #121216;
  --surface-2: #1a1a20;
  --border: #232329;
  --border-hover: #33333d;
  --text: #eeeef2;
  --text-dim: #97979f;
  --text-faint: #5f5f68;
  --accent: #8b7cf6;
  --accent-2: #5aa8e8;
  --accent-glow: rgba(139, 124, 246, 0.25);
  --green: #3ba55d;
  --amber: #f0a83a;
}
html { scroll-behavior: smooth; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  min-height: 100vh;
  overflow-x: hidden;
  position: relative;
}
body::before {
  content: "";
  position: fixed;
  inset: 0;
  z-index: -1;
  background:
    radial-gradient(ellipse 800px 500px at 20% -10%, rgba(139, 124, 246, 0.16), transparent 60%),
    radial-gradient(ellipse 700px 500px at 100% 10%, rgba(90, 168, 232, 0.10), transparent 60%);
}
a { color: inherit; text-decoration: none; }
img { max-width: 100%; display: block; }

.nav {
  position: sticky; top: 0; z-index: 20;
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px clamp(16px, 4vw, 40px);
  background: rgba(8, 8, 11, 0.72);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border-bottom: 1px solid var(--border);
}
.nav-brand { display: flex; align-items: center; gap: 10px; font-weight: 700; font-size: clamp(15px, 2.4vw, 17px); letter-spacing: -0.01em; }
.nav-brand img {
  width: 30px; height: 30px; border-radius: 9px;
  border: 1px solid var(--border);
}
.nav-links { display: flex; gap: clamp(14px, 3vw, 30px); font-size: 14px; color: var(--text-dim); }
.nav-links a { position: relative; padding: 4px 0; transition: color 0.2s ease; }
.nav-links a:hover { color: var(--text); }
.nav-links a::after {
  content: ""; position: absolute; left: 0; bottom: -2px; width: 0; height: 1.5px;
  background: var(--accent); transition: width 0.25s ease;
}
.nav-links a:hover::after { width: 100%; }

.container { max-width: 1040px; margin: 0 auto; padding: 0 clamp(16px, 4vw, 24px); }

.hero { text-align: center; padding: clamp(56px, 10vw, 96px) 20px clamp(40px, 6vw, 64px); }
.hero-logo {
  width: 88px; height: 88px; border-radius: 22px;
  border: 1px solid var(--border);
  margin: 0 auto 26px;
  box-shadow: 0 12px 40px rgba(0,0,0,0.5);
}
.status-pill {
  display: inline-flex; align-items: center; gap: 8px;
  background: var(--surface); border: 1px solid var(--border);
  padding: 7px 16px; border-radius: 999px; font-size: 13px; color: var(--text-dim);
  margin-bottom: 26px;
}
.status-dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--green); box-shadow: 0 0 10px var(--green);
  animation: pulse 2s ease-in-out infinite;
}
.status-dot.starting { background: var(--amber); box-shadow: 0 0 10px var(--amber); }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }

.hero h1 {
  font-size: clamp(34px, 7vw, 56px); font-weight: 800; letter-spacing: -0.03em; line-height: 1.05;
  background: linear-gradient(135deg, #fff 20%, #a89af5 75%, #7cc2f0 100%);
  -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
  margin-bottom: 18px;
}
.hero p {
  color: var(--text-dim); font-size: clamp(14.5px, 2vw, 17px);
  max-width: 580px; margin: 0 auto 34px; line-height: 1.65;
}
.hero-buttons { display: flex; gap: 14px; justify-content: center; flex-wrap: wrap; }
.btn {
  padding: 13px 28px; border-radius: 11px; font-weight: 600; font-size: 14px;
  border: 1px solid var(--border);
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease, background 0.18s ease;
  display: inline-block;
}
.btn:hover { transform: translateY(-2px); }
.btn-primary {
  background: linear-gradient(135deg, var(--accent), var(--accent-2));
  border-color: transparent; color: #fff;
}
.btn-primary:hover { box-shadow: 0 10px 30px var(--accent-glow); }
.btn-secondary { background: var(--surface); color: var(--text); }
.btn-secondary:hover { border-color: var(--border-hover); background: var(--surface-2); }

.stats-grid {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px;
  margin: 0 auto clamp(50px, 8vw, 80px); max-width: 920px; padding: 0 clamp(16px, 4vw, 24px);
}
.stat-card {
  background: var(--surface); border: 1px solid var(--border); border-radius: 14px;
  padding: 22px 16px; text-align: center;
  transition: border-color 0.2s ease, transform 0.2s ease;
}
.stat-card:hover { border-color: var(--border-hover); transform: translateY(-3px); }
.stat-value {
  font-size: clamp(20px, 3.4vw, 28px); font-weight: 700; margin-bottom: 4px;
  font-variant-numeric: tabular-nums;
}
.stat-label { font-size: 11.5px; color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.07em; }

.section { padding: clamp(36px, 6vw, 56px) clamp(16px, 4vw, 24px); }
.section-title { font-size: clamp(22px, 4vw, 27px); font-weight: 700; margin-bottom: 8px; text-align: center; letter-spacing: -0.01em; }
.section-sub { color: var(--text-dim); text-align: center; margin-bottom: clamp(30px, 5vw, 46px); font-size: clamp(13px, 2vw, 14.5px); }

.feature-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.feature-card {
  background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 26px 22px;
  transition: border-color 0.2s ease, transform 0.2s ease, background 0.2s ease;
}
.feature-card:hover { border-color: var(--border-hover); transform: translateY(-3px); background: var(--surface-2); }
.feature-card .mark {
  width: 34px; height: 34px; border-radius: 9px; margin-bottom: 14px;
  background: linear-gradient(135deg, var(--accent), var(--accent-2));
  display: flex; align-items: center; justify-content: center;
  font-size: 15px; font-weight: 700; color: #fff;
}
.feature-card h3 { font-size: 15.5px; margin-bottom: 8px; font-weight: 600; }
.feature-card p { color: var(--text-dim); font-size: 13px; line-height: 1.65; }

.card-list { display: flex; flex-direction: column; gap: 12px; }
.category-card {
  background: var(--surface); border: 1px solid var(--border); border-radius: 14px;
  padding: 20px 22px; transition: border-color 0.2s ease;
}
.category-card:hover { border-color: var(--border-hover); }
.category-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.category-header h3 { font-size: 15px; font-weight: 600; }
.category-count {
  color: var(--text-faint); font-size: 11.5px; background: var(--surface-2);
  padding: 3px 10px; border-radius: 999px; white-space: nowrap;
}
.category-desc { color: var(--text-dim); font-size: 13px; margin-top: 8px; line-height: 1.5; }
.command-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
.chip {
  background: var(--surface-2); border: 1px solid var(--border); border-radius: 8px;
  padding: 7px 12px; font-size: 12.5px; font-family: 'SF Mono', Consolas, monospace; color: var(--text-dim);
  transition: border-color 0.15s ease;
}
.chip:hover { border-color: var(--border-hover); }
.chip strong { color: var(--text); font-weight: 600; }
.chip .desc { color: var(--text-faint); font-family: inherit; margin-left: 4px; }

.dev-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 16px; }
.dev-card {
  background: var(--surface); border: 1px solid var(--border); border-radius: 16px;
  padding: 26px 20px; text-align: center;
  transition: border-color 0.2s ease, transform 0.2s ease;
}
.dev-card:hover { border-color: var(--border-hover); transform: translateY(-3px); }
.dev-avatar {
  width: 74px; height: 74px; border-radius: 50%; margin: 0 auto 14px;
  border: 2px solid var(--border); object-fit: cover;
}
.dev-name { font-weight: 600; font-size: 14.5px; margin-bottom: 8px; }
.dev-role {
  display: inline-block; font-size: 10.5px; color: var(--accent);
  background: rgba(139, 124, 246, 0.12); padding: 4px 11px; border-radius: 999px;
  text-transform: uppercase; letter-spacing: 0.05em; font-weight: 700;
}

.footer {
  text-align: center; padding: 36px 20px; color: var(--text-faint); font-size: 12.5px;
  border-top: 1px solid var(--border); margin-top: 30px;
}

.search-box {
  width: 100%; max-width: 440px; margin: 0 auto 30px; display: block;
  background: var(--surface); border: 1px solid var(--border); border-radius: 11px;
  padding: 13px 18px; color: var(--text); font-size: 14px;
  transition: border-color 0.2s ease;
}
.search-box:focus { outline: none; border-color: var(--accent); }
.search-box::placeholder { color: var(--text-faint); }

.empty-state { text-align: center; color: var(--text-faint); padding: 70px 0; font-size: 14px; }

@media (max-width: 760px) {
  .stats-grid { grid-template-columns: repeat(2, 1fr); }
  .feature-grid { grid-template-columns: 1fr; }
  .nav { padding: 14px 16px; }
  .nav-links { gap: 14px; font-size: 12.5px; }
  .hero { padding: 44px 16px 36px; }
  .hero-buttons { flex-direction: column; width: 100%; max-width: 320px; margin: 0 auto; }
  .hero-buttons .btn { width: 100%; text-align: center; }
  .dev-grid { grid-template-columns: repeat(2, 1fr); gap: 12px; }
  .category-header { flex-wrap: wrap; row-gap: 6px; }
}
@media (max-width: 480px) {
  .nav-brand span.brand-text { display: none; }
  .category-header { flex-direction: column; align-items: flex-start; }
  .stats-grid { grid-template-columns: repeat(2, 1fr); gap: 10px; }
  .stat-card { padding: 16px 10px; }
  .dev-grid { grid-template-columns: 1fr 1fr; }
  .chip { font-size: 11.5px; padding: 6px 10px; }
  .hero-logo { width: 68px; height: 68px; }
  .status-pill { font-size: 11.5px; padding: 6px 12px; text-align: center; }
}
@media (max-width: 360px) {
  .dev-grid { grid-template-columns: 1fr; }
}
"""


def base_page(title: str, body: str, *, bot_avatar_url: str = "") -> str:
    logo_html = f'<img src="{bot_avatar_url}" alt="{config.BOT_NAME}">' if bot_avatar_url else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{config.BOT_NAME} — an all-in-one Discord bot for moderation, security, music, and utility.">
<link rel="icon" href="{bot_avatar_url}">
<style>{BASE_CSS}</style>
</head>
<body>
{_nav(logo_html)}
{body}
{_footer()}
</body>
</html>"""


def _nav(logo_html: str) -> str:
    return f"""<nav class="nav">
  <div class="nav-brand">{logo_html}<span class="brand-text">{config.BOT_NAME}</span></div>
  <div class="nav-links">
    <a href="/">Home</a>
    <a href="/commands">Commands</a>
    <a href="/devs">Developers</a>
  </div>
</nav>"""


def _footer() -> str:
    return f"""<div class="footer">{config.BOT_NAME} v{config.BOT_VERSION} · Made by Soward Team</div>"""
