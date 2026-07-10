import os
import re

import httpx
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL   = os.environ.get("API_BASE_URL", "http://localhost:8000")
API_URL        = f"{API_BASE_URL}/chat"
AUTH_LOGIN_URL = f"{API_BASE_URL}/auth/login"
AUTH_REFRESH_URL = f"{API_BASE_URL}/auth/refresh"

SERVICE_ACCOUNT_USERNAME = os.environ.get("SERVICE_ACCOUNT_USERNAME")
SERVICE_ACCOUNT_PASSWORD = os.environ.get("SERVICE_ACCOUNT_PASSWORD")


def _login() -> dict:
    """Authentifie le service Streamlit auprès de l'API (compte de service, pas d'utilisateur final)."""
    response = httpx.post(
        AUTH_LOGIN_URL,
        json={"username": SERVICE_ACCOUNT_USERNAME, "password": SERVICE_ACCOUNT_PASSWORD},
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()


def _refresh_tokens(refresh_token: str) -> dict:
    response = httpx.post(AUTH_REFRESH_URL, json={"refresh_token": refresh_token}, timeout=10.0)
    response.raise_for_status()
    return response.json()


def _authenticated_post(url: str, json: dict, timeout: float) -> httpx.Response:
    """
    POST authentifié : joint l'access token courant, se ré-authentifie
    automatiquement (refresh, puis login si besoin) sur un 401 — invisible
    pour l'utilisateur du chatbot.
    """
    if "tokens" not in st.session_state:
        st.session_state.tokens = _login()

    def _post_with_current_token() -> httpx.Response:
        headers = {"Authorization": f"Bearer {st.session_state.tokens['access_token']}"}
        return httpx.post(url, json=json, headers=headers, timeout=timeout)

    response = _post_with_current_token()

    if response.status_code == 401:
        try:
            st.session_state.tokens = _refresh_tokens(st.session_state.tokens["refresh_token"])
        except httpx.HTTPStatusError:
            st.session_state.tokens = _login()
        response = _post_with_current_token()

    return response


def _sanitize_markdown(text: str) -> str:
    """
    Évite les « setext headings » : une ligne de tirets (ou de '=') collée
    directement sous du texte transforme tout le bloc au-dessus en titre géant.
    On insère une ligne vide avant, ce qui en fait une simple ligne horizontale.
    """
    lines = text.split("\n")
    out: list[str] = []
    for line in lines:
        if re.fullmatch(r"\s*[-=]{3,}\s*", line) and out and out[-1].strip():
            out.append("")
        out.append(line)
    return "\n".join(out)

# ── Moon ─────────────────────────────────────────────────────────────────────
_MOON = """<svg viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg" width="180" height="180">
  <defs>
    <radialGradient id="mhalo" cx="50%" cy="50%" r="50%">
      <stop offset="0%"   stop-color="#8b2020" stop-opacity="0.38"/>
      <stop offset="55%"  stop-color="#5a1010" stop-opacity="0.14"/>
      <stop offset="100%" stop-color="#000"    stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="msurf" cx="42%" cy="38%" r="50%">
      <stop offset="0%"   stop-color="#f7edcc"/>
      <stop offset="65%"  stop-color="#e8d090"/>
      <stop offset="100%" stop-color="#c8a055"/>
    </radialGradient>
    <filter id="mglow">
      <feGaussianBlur in="SourceGraphic" stdDeviation="7" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>
  <circle cx="100" cy="100" r="98"  fill="url(#mhalo)"/>
  <circle cx="100" cy="100" r="52"  fill="url(#msurf)" filter="url(#mglow)"/>
  <circle cx="84"  cy="88"  r="7"   fill="#d4a855" opacity="0.45"/>
  <circle cx="113" cy="110" r="4.5" fill="#c89848" opacity="0.35"/>
  <circle cx="96"  cy="116" r="3.5" fill="#d4a855" opacity="0.30"/>
  <circle cx="108" cy="86"  r="2.5" fill="#c89848" opacity="0.25"/>
</svg>"""

# ── Castle (30 % bigger: 400→520 x 310→403) ───────────────────────────────
_CASTLE = """<svg viewBox="0 0 400 310" xmlns="http://www.w3.org/2000/svg" width="520" height="403">
<defs>
  <filter id="wglow" x="-150%" y="-150%" width="400%" height="400%">
    <feGaussianBlur in="SourceGraphic" stdDeviation="6" result="b"/>
    <feMerge><feMergeNode in="b"/><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
</defs>
<style>
  .cw  { animation: cflicker  3.2s ease-in-out infinite; }
  .cw2 { animation: cflicker2 4.1s ease-in-out infinite 0.6s; }
  .cw3 { animation: cflicker3 2.7s ease-in-out infinite 1.3s; }
  @keyframes cflicker  { 0%,100%{opacity:.95} 20%{opacity:.60} 55%{opacity:1}  80%{opacity:.50} }
  @keyframes cflicker2 { 0%,100%{opacity:.90} 30%{opacity:.55} 60%{opacity:.95} 85%{opacity:.65} }
  @keyframes cflicker3 { 0%,100%{opacity:.85} 15%{opacity:.70} 50%{opacity:1}  75%{opacity:.45} }
</style>
<g fill="#1a1210">
  <polygon points="10,170 24,215 38,170"/>
  <rect x="10" y="204" width="6"  height="13"/>
  <rect x="20" y="204" width="6"  height="13"/>
  <rect x="30" y="204" width="6"  height="13"/>
  <rect x="13" y="213" width="22" height="97"/>
  <rect x="35" y="258" width="20" height="52"/>
  <polygon points="54,112 76,162 98,112"/>
  <rect x="54" y="152" width="11" height="13"/>
  <rect x="69" y="152" width="11" height="13"/>
  <rect x="84" y="152" width="11" height="13"/>
  <rect x="52" y="162" width="48" height="148"/>
  <rect x="100" y="215" width="26" height="95"/>
  <rect x="157" y="70"  width="86" height="62"/>
  <rect x="157" y="55"  width="13" height="18"/>
  <rect x="174" y="55"  width="13" height="18"/>
  <rect x="191" y="55"  width="13" height="18"/>
  <rect x="208" y="55"  width="13" height="18"/>
  <rect x="225" y="55"  width="13" height="18"/>
  <rect x="118" y="130" width="164" height="180"/>
  <rect x="118" y="116" width="17" height="17"/>
  <rect x="139" y="116" width="17" height="17"/>
  <rect x="160" y="116" width="17" height="17"/>
  <rect x="181" y="116" width="17" height="17"/>
  <rect x="202" y="116" width="17" height="17"/>
  <rect x="223" y="116" width="17" height="17"/>
  <rect x="244" y="116" width="17" height="17"/>
  <rect x="265" y="116" width="17" height="17"/>
  <path d="M172,310 L172,262 Q200,235 228,262 L228,310 Z" fill="#130808"/>
  <rect x="274" y="215" width="26" height="95"/>
  <polygon points="302,112 324,162 346,112"/>
  <rect x="302" y="152" width="11" height="13"/>
  <rect x="317" y="152" width="11" height="13"/>
  <rect x="332" y="152" width="11" height="13"/>
  <rect x="300" y="162" width="48" height="148"/>
  <rect x="345" y="258" width="20" height="52"/>
  <polygon points="362,170 376,215 390,170"/>
  <rect x="362" y="204" width="6"  height="13"/>
  <rect x="372" y="204" width="6"  height="13"/>
  <rect x="382" y="204" width="6"  height="13"/>
  <rect x="365" y="213" width="22" height="97"/>
</g>
<rect class="cw"  x="70"  y="195" width="13" height="24" rx="6"  fill="#e88a0a" filter="url(#wglow)"/>
<rect class="cw3" x="142" y="162" width="14" height="30" rx="7"  fill="#f09520" filter="url(#wglow)"/>
<rect class="cw2" x="182" y="150" width="36" height="52" rx="18" fill="#e88a0a" filter="url(#wglow)"/>
<rect class="cw"  x="248" y="162" width="14" height="30" rx="7"  fill="#f09520" filter="url(#wglow)"/>
<rect class="cw3" x="317" y="195" width="13" height="24" rx="6"  fill="#e88a0a" filter="url(#wglow)"/>
</svg>"""

# ── Hills ─────────────────────────────────────────────────────────────────────
_HILLS = """<svg viewBox="0 0 1200 160" preserveAspectRatio="none"
     xmlns="http://www.w3.org/2000/svg" width="100%" height="160">
  <path d="M0,160 L0,88 Q130,28 250,72 Q400,118 530,50
           Q660,4 790,60 Q930,118 1060,46 Q1140,12 1200,68
           L1200,160 Z" fill="#0d0b0b"/>
  <path d="M0,160 L0,118 Q90,86 200,108 Q340,132 460,100
           Q590,70 720,108 Q850,136 980,96
           Q1080,74 1200,114 L1200,160 Z" fill="#090707"/>
</svg>"""

# ── Bat ───────────────────────────────────────────────────────────────────────
_BAT = """<svg class="bat-svg" viewBox="-32 -22 64 44"
     xmlns="http://www.w3.org/2000/svg" width="56" height="38">
  <ellipse cx="0" cy="2" rx="5" ry="6" fill="#110c0c"/>
  <polygon points="-4,-5 -8,-15 -2,-6"  fill="#110c0c"/>
  <polygon points="4,-5  8,-15  2,-6"   fill="#110c0c"/>
  <path d="M-5,0 C-12,-14 -30,-6 -30,4 C-23,10 -17,6 -11,9 C-8,5 -6,2 -5,0 Z" fill="#0e0a0a"/>
  <path d="M5,0  C12,-14  30,-6  30,4 C23,10  17,6  11,9 C8,5  6,2  5,0 Z"    fill="#0e0a0a"/>
</svg>"""

# ── Cloud ─────────────────────────────────────────────────────────────────────
# viewBox bottom (y=0) = landing surface; cloud mass sits above
_CLOUD = """<svg viewBox="-65 -45 130 45"
     xmlns="http://www.w3.org/2000/svg" width="130" height="45">
  <ellipse cx="0"   cy="-22" rx="58" ry="20" fill="#1c1420"/>
  <ellipse cx="-22" cy="-30" rx="30" ry="15" fill="#211828"/>
  <ellipse cx="22"  cy="-33" rx="34" ry="17" fill="#211828"/>
  <ellipse cx="0"   cy="-38" rx="22" ry="12" fill="#261e2e"/>
</svg>"""

# ── Zombie ────────────────────────────────────────────────────────────────────
_ZOMBIE = """<svg class="zombie-svg" viewBox="-15 -46 30 48"
     xmlns="http://www.w3.org/2000/svg" width="36" height="58">
  <ellipse cx="0"    cy="-39" rx="6"   ry="7"   fill="#1a1e10"/>
  <rect    x="-5.5"  y="-32"  width="11" height="16" fill="#171b0f" rx="1"/>
  <line x1="-5.5" y1="-26" x2="-14" y2="-30" stroke="#1a1e10" stroke-width="3.5" stroke-linecap="round"/>
  <line x1="5.5"  y1="-26" x2="13"  y2="-29" stroke="#1a1e10" stroke-width="3.5" stroke-linecap="round"/>
  <g class="z-leg-l"><rect x="-5"   y="-16" width="4.5" height="14" rx="2" fill="#171b0f"/></g>
  <g class="z-leg-r"><rect x="0.5"  y="-16" width="4.5" height="14" rx="2" fill="#171b0f"/></g>
  <circle class="zombie-eye" cx="-2.5" cy="-40" r="1.3" fill="#dd1111"/>
  <circle class="zombie-eye" cx="2.5"  cy="-40" r="1.3" fill="#dd1111"/>
</svg>"""


def _inject_background() -> None:
    castle = _CASTLE.replace("`", "\\`").replace("\n", " ")
    hills  = _HILLS .replace("`", "\\`").replace("\n", " ")
    moon   = _MOON  .replace("`", "\\`").replace("\n", " ")
    bat    = _BAT   .replace("`", "\\`").replace("\n", " ")
    zombie = _ZOMBIE.replace("`", "\\`").replace("\n", " ")
    cloud  = _CLOUD .replace("`", "\\`").replace("\n", " ")

    components.html(f"""
<script>
(function() {{
  var par = window.parent;
  var doc = par.document;
  if (doc.getElementById('hg-bg')) return;

  // ── CSS ──────────────────────────────────────────────────────────────
  var style = doc.createElement('style');
  style.id = 'hg-style';
  style.textContent = `
    [data-testid="stAppViewContainer"],[data-testid="stApp"],
    .main,.main>div {{ background:transparent !important; }}
    [data-testid="stHeader"] {{ background:transparent !important; box-shadow:none !important; }}
    [data-testid="stBottom"] {{ background:transparent !important; }}
    body {{ background:#050202 !important; }}
    .bat-svg {{
      animation: bat-flap 0.25s ease-in-out infinite alternate;
      overflow: visible;
    }}
    @keyframes bat-flap {{
      0%   {{ transform: scaleY(1);   }}
      100% {{ transform: scaleY(0.5); }}
    }}
    .zombie-eye {{ filter: drop-shadow(0 0 3px #cc2222); }}
    @keyframes cloud-pulse {{
      0%,100% {{ opacity: 0.82; }}
      50%     {{ opacity: 0.55; }}
    }}
    @keyframes fog-a {{ 0%,100%{{transform:translateX(0);opacity:.7}} 50%{{transform:translateX(6%);opacity:.35}} }}
    @keyframes fog-b {{ 0%,100%{{transform:translateX(0);opacity:.5}} 50%{{transform:translateX(-5%);opacity:.25}} }}
    @keyframes fog-c {{ 0%,100%{{transform:translateX(0);opacity:.55}} 50%{{transform:translateX(8%);opacity:.20}} }}
    [data-testid="stChatInputContainer"] textarea::placeholder {{
      color: rgba(180,70,70,0.55) !important;
      font-style: italic;
    }}
    [data-testid="stChatMessage"] p,
    [data-testid="stChatMessage"] li,
    [data-testid="stChatMessage"] pre {{
      overflow-wrap: break-word !important;
      word-break: break-word !important;
      white-space: pre-wrap !important;
    }}
    [data-testid="stChatMessage"] pre {{
      overflow-x: auto !important;
      max-width: 100% !important;
    }}
  `;
  doc.head.appendChild(style);

  // ── Background container ──────────────────────────────────────────────
  var bg = doc.createElement('div');
  bg.id = 'hg-bg';
  bg.style.cssText =
    'position:fixed;inset:0;z-index:-1;overflow:hidden;' +
    'background:radial-gradient(ellipse at 50% -5%,' +
      '#6b2020 0%,#3d1010 18%,#1e0a0a 40%,#0d0505 65%,#050202 100%);';
  doc.body.insertBefore(bg, doc.body.firstChild);

  // ── Star canvas ───────────────────────────────────────────────────────
  var canvas = doc.createElement('canvas');
  canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;';
  bg.appendChild(canvas);
  var ctx = canvas.getContext('2d');
  function resize() {{ canvas.width = par.innerWidth; canvas.height = par.innerHeight; }}
  resize();
  par.addEventListener('resize', resize);
  var stars = Array.from({{length: 85}}, function() {{
    return {{
      x: Math.random(), y: Math.random() * 0.60,
      r: Math.random() * 1.3 + 0.35,
      phase: Math.random() * Math.PI * 2,
      speed: 0.3 + Math.random() * 1.3,
      base:  0.3 + Math.random() * 0.7
    }};
  }});

  // ── Moon (behind castle in DOM) ───────────────────────────────────────
  var moonEl = doc.createElement('div');
  moonEl.innerHTML = `{moon}`;
  moonEl.style.cssText = 'position:absolute;bottom:410px;right:470px;opacity:0.90;';
  bg.appendChild(moonEl);

  // ── Castle ────────────────────────────────────────────────────────────
  var castleEl = doc.createElement('div');
  castleEl.innerHTML = `{castle}`;
  castleEl.style.cssText = 'position:absolute;bottom:90px;right:1%;filter:drop-shadow(0 0 22px rgba(120,30,10,0.55));';
  bg.appendChild(castleEl);

  // ── Hills ─────────────────────────────────────────────────────────────
  var hillsEl = doc.createElement('div');
  hillsEl.innerHTML = `{hills}`;
  hillsEl.style.cssText = 'position:absolute;bottom:0;left:0;right:0;';
  bg.appendChild(hillsEl);

  // ── Zombie interactive overlay (above UI, pointer-events passthrough) ───
  var zombieOverlay = doc.createElement('div');
  zombieOverlay.id = 'hg-zombie-layer';
  // z-index très haut : passe devant le bandeau d'input Streamlit (stBottom)
  // pour que les zombies marchent par-dessus au lieu d'être masqués.
  zombieOverlay.style.cssText = 'position:fixed;inset:0;z-index:2147483000;pointer-events:none;overflow:visible;';
  doc.body.appendChild(zombieOverlay);

  // ── Zombies ────────────────────────────────────────────────────────────
  var GRAVITY   = 0.25;
  var dragState = {{ zombie: null, offsetX: 0, offsetY: 0, history: [] }};
  var zombies   = [];
  for (var i = 0; i < 8; i++) {{
    var zd = doc.createElement('div');
    zd.innerHTML = `{zombie}`;
    zd.style.cssText = 'position:absolute;pointer-events:auto;cursor:grab;user-select:none;';
    zombieOverlay.appendChild(zd);
    var groundY = 86 + Math.random() * 22;
    zombies.push({{
      el:          zd,
      x:           Math.random() * par.innerWidth,
      groundLevel: groundY,
      baseBottom:  groundY,
      vx:          (0.06 + Math.random() * 0.16) * (Math.random() > 0.5 ? 1 : -1),
      phase:       Math.random() * Math.PI * 2,
      scale:       0.72 + Math.random() * 0.50,
      thrown:      false,
      dragging:    false,
      throwHeight: 0,
      vy:          0,
      platform:    null,
      orbiting:    false,
      orbitAngle:  0,
      orbitVel:    0
    }});
  }}

  // ── Drag & throw handlers ─────────────────────────────────────────────
  zombies.forEach(function(z) {{
    z.el.addEventListener('mousedown', function(e) {{
      e.preventDefault();
      e.stopPropagation();
      dragState.zombie  = z;
      dragState.offsetX = e.clientX - z.x;
      // Exit orbit: convert polar position back to cartesian
      if (z.orbiting) {{
        var ofx     = moonCx + MOON_R * Math.sin(z.orbitAngle);
        var ofy_top = moonCy + MOON_R * Math.cos(z.orbitAngle);
        z.x           = ofx;
        z.baseBottom  = z.groundLevel;
        z.throwHeight = Math.max(0, (par.innerHeight - ofy_top) - z.groundLevel);
        z.orbiting    = false;
        z.el.style.top             = '';
        z.el.style.transformOrigin = '';
      }}
      // Detach from any platform and normalise coords to groundLevel
      var curVisual = z.baseBottom + z.throwHeight;
      z.platform    = null;
      z.baseBottom  = z.groundLevel;
      z.throwHeight = Math.max(0, curVisual - z.groundLevel);
      dragState.offsetY = (par.innerHeight - e.clientY) - curVisual;
      dragState.history = [{{ x: e.clientX, y: e.clientY, t: Date.now() }}];
      z.dragging = true;
      z.thrown   = false;
      z.el.style.cursor = 'grabbing';
      z.el.style.zIndex = '200';
      doc.body.style.userSelect = 'none';
    }});
  }});

  doc.addEventListener('mousemove', function(e) {{
    if (!dragState.zombie) return;
    var z = dragState.zombie;
    z.x = e.clientX - dragState.offsetX;
    var visualBottom = (par.innerHeight - e.clientY) - dragState.offsetY;
    // throwHeight = extra height above fixed ground; clamped to [0, 85vh above ground]
    z.throwHeight = Math.max(0, Math.min(
      par.innerHeight * 0.85 - z.baseBottom,
      visualBottom - z.baseBottom
    ));
    dragState.history.push({{ x: e.clientX, y: e.clientY, t: Date.now() }});
    if (dragState.history.length > 8) dragState.history.shift();
  }});

  function releaseDrag(withThrow) {{
    if (!dragState.zombie) return;
    var z    = dragState.zombie;
    var hist = dragState.history;
    var vx = 0, vy = 0;
    if (withThrow && hist.length >= 2) {{
      var dt = Math.max(hist[hist.length - 1].t - hist[0].t, 16);
      vx = (hist[hist.length - 1].x - hist[0].x) / dt * 16;
      vy = -(hist[hist.length - 1].y - hist[0].y) / dt * 16;
    }}
    z.vx = Math.max(-8, Math.min(8, vx));
    if (Math.abs(z.vx) < 0.05) z.vx = 0.08 * (Math.random() > 0.5 ? 1 : -1);
    if (z.throwHeight > 0 || vy > 0.5) {{
      // zombie is in the air or was thrown up — gravity will bring it to baseBottom
      z.vy     = withThrow ? Math.min(14, vy) : 0;
      z.thrown = true;
    }} else {{
      // already at ground level, resume walking
      z.thrown      = false;
      z.throwHeight = 0;
      var dir = z.vx >= 0 ? 1 : -1;
      z.vx = dir * (0.06 + Math.random() * 0.10);
    }}
    z.dragging = false;
    dragState.zombie = null;
    z.el.style.cursor = 'grab';
    z.el.style.zIndex = '';
    doc.body.style.userSelect = '';
  }}

  doc.addEventListener('mouseup',    function() {{ releaseDrag(true);  }});
  doc.addEventListener('mouseleave', function() {{ releaseDrag(false); }});

  // ── Fog layers ────────────────────────────────────────────────────────
  [
    {{ b:60,  h:48, a:'fog-a', d:'18s', dl:'0s'   }},
    {{ b:88,  h:32, a:'fog-b', d:'25s', dl:'-9s'  }},
    {{ b:112, h:22, a:'fog-c', d:'21s', dl:'-15s' }}
  ].forEach(function(f) {{
    var fog = doc.createElement('div');
    fog.style.cssText =
      'position:absolute;bottom:' + f.b + 'px;left:-10%;right:-10%;height:' + f.h + 'px;' +
      'background:radial-gradient(ellipse at 50% 80%,' +
        'rgba(200,200,220,.09) 0%,rgba(180,180,210,.04) 55%,transparent 100%);' +
      'border-radius:50%;pointer-events:none;' +
      'animation:' + f.a + ' ' + f.d + ' ease-in-out infinite ' + f.dl + ';';
    bg.appendChild(fog);
  }});

  // ── Bats (12) ─────────────────────────────────────────────────────────
  var bats = [];
  for (var i = 0; i < 12; i++) {{
    var bd = doc.createElement('div');
    bd.innerHTML = `{bat}`;
    bd.style.cssText = 'position:absolute;pointer-events:none;';
    bg.appendChild(bd);
    bats.push({{
      el:     bd,
      x:      Math.random() * par.innerWidth,
      y:      30 + Math.random() * (par.innerHeight * 0.45),
      vx:     (0.2 + Math.random() * 0.8) * (Math.random() > 0.5 ? 1 : -1),
      yAmp:   10 + Math.random() * 28,
      yFreq:  0.3 + Math.random() * 0.7,
      yPhase: Math.random() * Math.PI * 2
    }});
  }}

  // ── Clouds (3 drifting platforms) ─────────────────────────────────────
  // landingY = height from bottom where zombie feet touch the cloud top
  var CLOUD_HALF_W = 58; // base half-width matching SVG rx
  var cloudDefs = [
    {{ landingY: 210, startX: 0.20, vx:  0.12, scale: 0.90, delay: '0s'   }},
    {{ landingY: 345, startX: 0.55, vx: -0.16, scale: 1.10, delay: '3.5s' }},
    {{ landingY: 262, startX: 0.78, vx:  0.22, scale: 0.75, delay: '7s'   }}
  ];
  var clouds = cloudDefs.map(function(cd) {{
    var cel = doc.createElement('div');
    cel.innerHTML = `{cloud}`;
    cel.style.cssText =
      'position:absolute;pointer-events:none;transform-origin:bottom center;' +
      'animation:cloud-pulse ' + (8 + Math.random() * 5).toFixed(1) + 's ease-in-out infinite ' + cd.delay + ';';
    bg.appendChild(cel);
    return {{
      el:       cel,
      x:        cd.startX * par.innerWidth,
      landingY: cd.landingY,
      vx:       cd.vx,
      scale:    cd.scale,
      halfWidth: CLOUD_HALF_W * cd.scale
    }};
  }});

  // ── Castle platforms (static ledges derived from SVG geometry) ────────
  // Castle: viewBox 400×310 → rendered 520×403 → scale 1.3
  // CSS:    bottom:90px  right:1%
  // castleX0 = left edge of castle (recalculated on resize)
  var CASTLE_SCALE = 403 / 310; // = 1.3
  var CASTLE_H     = 403;
  var CASTLE_W     = 520;
  var CASTLE_BOT   = 90; // CSS bottom in px
  // SVG geometry: [cx, half-width, top-surface y]
  var _cpSVG = [
    [200, 82,  116], // main keep battlements
    [76,  24,  152], // left mid-tower
    [324, 24,  152], // right mid-tower
    [24,  11,  204], // left small tower
    [376, 11,  204]  // right small tower
  ];
  function _makeCastle() {{
    var cx0 = par.innerWidth * 0.99 - CASTLE_W;
    return _cpSVG.map(function(p) {{
      return {{
        x:         cx0 + p[0] * CASTLE_SCALE,
        landingY:  Math.round(CASTLE_BOT + CASTLE_H - p[2] * CASTLE_SCALE),
        halfWidth: p[1] * CASTLE_SCALE,
        vx:        0
      }};
    }});
  }}
  var castlePlatforms = _makeCastle();
  par.addEventListener('resize', function() {{ castlePlatforms = _makeCastle(); }});

  // ── Moon orbital constants ─────────────────────────────────────────────
  // Moon CSS: bottom:410px right:470px  — SVG 180×180 (viewBox 200×200)
  // Moon surface circle: r=52 in SVG → r=52*(180/200)=46.8 rendered
  var MOON_R = 50; // orbit radius (zombie feet on moon surface)
  var moonCx = par.innerWidth  - 560; // center X from viewport left (right:470 + 90)
  var moonCy = par.innerHeight - 500; // center Y from viewport top  (bottom:410 + 90)
  par.addEventListener('resize', function() {{
    moonCx = par.innerWidth  - 560;
    moonCy = par.innerHeight - 500;
  }});

  // ── Animation loop ────────────────────────────────────────────────────
  function draw(t) {{
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Stars
    stars.forEach(function(s) {{
      var a = s.base * (0.5 + 0.5 * Math.sin(t * s.speed + s.phase));
      ctx.beginPath();
      ctx.arc(s.x * canvas.width, s.y * canvas.height, s.r, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(255,248,220,' + a.toFixed(3) + ')';
      ctx.fill();
    }});

    // Zombies
    var W = par.innerWidth;
    zombies.forEach(function(z) {{
      var lL = z.el.querySelector('.z-leg-l');
      var lR = z.el.querySelector('.z-leg-r');

      if (z.dragging) {{
        // Held — flail legs rapidly
        var la = Math.sin(t * 14 + z.phase) * 50;
        var flip = z.vx >= 0 ? 'scaleX(1)' : 'scaleX(-1)';
        z.el.style.left      = z.x + 'px';
        z.el.style.bottom    = (z.baseBottom + z.throwHeight) + 'px';
        z.el.style.transform = flip + ' scale(' + z.scale + ')';
        if (lL) lL.setAttribute('transform', 'rotate(' + la    + ' -2.75 -16)');
        if (lR) lR.setAttribute('transform', 'rotate(' + (-la) + '  2.75 -16)');
        return;
      }}

      if (z.orbiting) {{
        z.orbitAngle += z.orbitVel;
        var sinA = Math.sin(z.orbitAngle);
        var cosA = Math.cos(z.orbitAngle);
        var feetX    = moonCx + MOON_R * sinA;
        var feetY_t  = moonCy + MOON_R * cosA; // viewport top-based
        z.x = feetX;
        // Position div so its bottom-center = feet point
        z.el.style.left            = (feetX - 18) + 'px'; // 18 = half of 36px SVG width
        z.el.style.top             = (feetY_t - 58) + 'px'; // 58 = SVG height
        z.el.style.bottom          = '';
        z.el.style.transformOrigin = 'center bottom';
        var thetaDeg = z.orbitAngle * (180 / Math.PI);
        // Flip based on orbit direction so zombie faces forward
        var fwd = z.orbitVel >= 0 ? 'scaleX(1)' : 'scaleX(-1)';
        z.el.style.transform = 'rotate(' + thetaDeg + 'deg) ' + fwd + ' scale(' + z.scale + ')';
        var la = Math.sin(t * 3.5 + z.phase) * 22;
        if (lL) lL.setAttribute('transform', 'rotate(' + la    + ' -2.75 -16)');
        if (lR) lR.setAttribute('transform', 'rotate(' + (-la) + '  2.75 -16)');
        return;
      }}

      if (z.thrown) {{
        var prevFeetY = z.baseBottom + z.throwHeight;
        z.vy          -= GRAVITY;
        z.throwHeight += z.vy;
        var newFeetY   = z.baseBottom + z.throwHeight;
        // ── Cloud landing (only while falling) ──────────────────────────
        var landed = false;
        if (z.vy < 0) {{
          // Check cloud platforms
          clouds.forEach(function(c) {{
            if (landed) return;
            if (prevFeetY >= c.landingY && newFeetY <= c.landingY) {{
              if (Math.abs(z.x - c.x) <= c.halfWidth) {{
                z.platform    = c;
                z.baseBottom  = c.landingY;
                z.throwHeight = 0;
                z.thrown      = false;
                landed        = true;
                var dir = z.vx >= 0 ? 1 : -1;
                z.vx = dir * (0.06 + Math.random() * 0.12);
              }}
            }}
          }});
          // Check castle platforms
          if (!landed) castlePlatforms.forEach(function(c) {{
            if (landed) return;
            if (prevFeetY >= c.landingY && newFeetY <= c.landingY) {{
              if (Math.abs(z.x - c.x) <= c.halfWidth) {{
                z.platform    = c;
                z.baseBottom  = c.landingY;
                z.throwHeight = 0;
                z.thrown      = false;
                landed        = true;
                var dir = z.vx >= 0 ? 1 : -1;
                z.vx = dir * (0.06 + Math.random() * 0.12);
              }}
            }}
          }});
        }}
        // ── Moon landing (any direction) ─────────────────────────────────
        if (!landed) {{
          var feetY_top = par.innerHeight - (z.baseBottom + z.throwHeight);
          var dx = z.x - moonCx;
          var dy = feetY_top - moonCy;
          if (Math.sqrt(dx * dx + dy * dy) <= MOON_R + 14) {{
            var angle = Math.atan2(dx, dy); // 0=bottom, +π/2=right, +π=top
            z.orbitAngle = angle;
            var baseOV   = 0.015 + Math.random() * 0.012;
            z.orbitVel   = z.vx >= 0 ? baseOV : -baseOV;
            z.orbiting   = true;
            z.thrown     = false;
            z.platform   = null;
            landed       = true;
          }}
        }}
        // ── Ground landing ───────────────────────────────────────────────
        if (!landed && newFeetY <= z.groundLevel) {{
          z.baseBottom  = z.groundLevel;
          z.throwHeight = 0;
          z.thrown      = false;
          z.platform    = null;
          var dir = z.vx >= 0 ? 1 : -1;
          z.vx = dir * (0.06 + Math.random() * 0.12);
        }}
        z.x += z.vx;
        if (z.x >  W + 40) z.x = -40;
        if (z.x < -40)     z.x =  W + 40;
        z.el.style.left   = z.x + 'px';
        z.el.style.bottom = (z.baseBottom + z.throwHeight) + 'px';
        var tilt = Math.max(-45, Math.min(45, -z.vy * 4));
        var flip = z.vx >= 0 ? 'scaleX(1)' : 'scaleX(-1)';
        z.el.style.transform = flip + ' scale(' + z.scale + ') rotate(' + tilt + 'deg)';
        var la = Math.sin(t * 10 + z.phase) * 50;
        if (lL) lL.setAttribute('transform', 'rotate(' + la    + ' -2.75 -16)');
        if (lR) lR.setAttribute('transform', 'rotate(' + (-la) + '  2.75 -16)');
        return;
      }}

      // Normal walk (ground or cloud platform)
      if (z.platform) {{
        z.baseBottom = z.platform.landingY;  // track cloud Y
        z.x         += z.platform.vx;        // carried by cloud
        // Edge detection — fall off when past cloud bounds
        if (Math.abs(z.x - z.platform.x) > z.platform.halfWidth + 4) {{
          z.platform = null;
          z.thrown   = true;
          z.vy       = 0;
        }}
      }}
      z.x += z.vx;
      if (z.x >  W + 40) z.x = -40;
      if (z.x < -40)     z.x =  W + 40;
      var bob = 1.8 * Math.abs(Math.sin(t * 3.5 + z.phase));
      z.el.style.left   = z.x + 'px';
      z.el.style.bottom = (z.baseBottom + bob) + 'px';
      var flip = z.vx < 0 ? 'scaleX(-1)' : 'scaleX(1)';
      z.el.style.transform = flip + ' scale(' + z.scale + ')';
      var la = Math.sin(t * 3.5 + z.phase) * 22;
      if (lL) lL.setAttribute('transform', 'rotate(' + la       + ' -2.75 -16)');
      if (lR) lR.setAttribute('transform', 'rotate(' + (-la)    + '  2.75 -16)');
    }});

    // Clouds
    clouds.forEach(function(c) {{
      c.x += c.vx;
      if (c.x - c.halfWidth >  W + 10) c.x = -c.halfWidth;
      if (c.x + c.halfWidth < -10)     c.x =  W + c.halfWidth;
      c.el.style.left      = (c.x - 65) + 'px'; // center at c.x; scale handled by transform-origin
      c.el.style.bottom    = c.landingY + 'px';
      c.el.style.transform = 'scale(' + c.scale + ')';
    }});

    // Bats
    bats.forEach(function(b) {{
      b.x += b.vx;
      var W = canvas.width;
      if (b.x >  W + 40) b.x = -40;
      if (b.x < -40)     b.x =  W + 40;
      var y = b.y + b.yAmp * Math.sin(t * b.yFreq + b.yPhase);
      b.el.style.left      = b.x + 'px';
      b.el.style.top       = y   + 'px';
      b.el.style.transform = b.vx < 0 ? 'scaleX(-1)' : 'scaleX(1)';
    }});

    par.requestAnimationFrame(function(ts) {{ draw(ts / 1000); }});
  }}
  par.requestAnimationFrame(function(ts) {{ draw(ts / 1000); }});

  // ── Style stBottom + input (no blood drip) ───────────────────────────
  function styleBottom() {{
    var stBot = doc.querySelector('[data-testid="stBottom"]');
    if (stBot) {{
      stBot.style.setProperty('background', 'linear-gradient(to top,#0f0303,#1e0606)', 'important');
      stBot.style.setProperty('border-top', 'none', 'important');
      stBot.style.setProperty('box-shadow', 'none', 'important');
    }}
    var inp = doc.querySelector('[data-testid="stChatInputContainer"]');
    if (inp) {{
      inp.style.setProperty('border', '1px solid rgba(139,0,0,0.5)', 'important');
      inp.style.setProperty('border-radius', '10px', 'important');
      inp.style.setProperty('box-shadow', '0 0 12px rgba(139,0,0,0.25)', 'important');
    }}
  }}
  styleBottom();
  setTimeout(styleBottom, 350);
  setTimeout(styleBottom, 1000);
  par.addEventListener('resize', styleBottom);

  // ── Assistant chat bubble styling (MutationObserver) ──────────────────
  function styleAssistantBubbles() {{
    doc.querySelectorAll('[data-testid="stChatMessage"]').forEach(function(msg) {{
      if (msg.getAttribute('data-hg-styled')) return;
      var isAssistant =
        msg.querySelector('[data-testid="chatAvatarIcon-assistant"]') ||
        msg.querySelector('img[alt="assistant"]') ||
        msg.querySelector('[aria-label*="assistant"]');
      if (isAssistant) {{
        msg.style.setProperty('background',    'rgba(65, 10, 30, 0.32)', 'important');
        msg.style.setProperty('border-radius', '12px',                   'important');
        msg.style.setProperty('border',        'none',                   'important');
        msg.style.setProperty('padding',       '10px 14px',              'important');
        msg.style.setProperty('overflow',      'visible',                'important');
        msg.style.setProperty('max-height',    'none',                   'important');
        msg.style.setProperty('width',         '100%',                   'important');
        msg.style.setProperty('box-sizing',    'border-box',             'important');
        msg.setAttribute('data-hg-styled', '1');
      }}
    }});
  }}
  styleAssistantBubbles();
  var chatObserver = new MutationObserver(styleAssistantBubbles);
  chatObserver.observe(doc.body, {{ childList: true, subtree: true }});
}})();
</script>
""", height=0)


# ── Juge verdict (bandeau bas) ────────────────────────────────────────────────

def _inject_judge_verdict(verdict: dict | None, tools_used: list | None = None) -> None:
    """Injecte le verdict du Juge dans le bandeau stBottom, style horreur."""
    if not verdict:
        return

    is_valid   = verdict.get("is_valid", True)
    confidence = verdict.get("confidence", 0.75)
    reasoning  = (verdict.get("reasoning") or "").replace('"', '&quot;').replace("'", "\\'")
    reasoning  = reasoning[:140] + ("…" if len(reasoning) > 140 else "")
    conf_pct   = int(confidence * 100)

    if is_valid and confidence >= 0.80:
        icon, color, label = "🩸", "#cc2222", "LE JUGE A APPROUVÉ"
    elif is_valid:
        icon, color, label = "⚠️", "#b85c00", "LE JUGE EST MITIGÉ"
    else:
        icon, color, label = "💀", "#8b0000", "LE JUGE CONDAMNE"

    tools_str  = " › ".join(t for t in (tools_used or []) if t != "groq-llm")
    tools_html = (
        f'<span style="color:rgba(139,0,0,0.6);flex-shrink:0;margin:0 2px">|</span>'
        f'<span style="color:rgba(140,100,100,0.75);flex-shrink:0;letter-spacing:0.5px">'
        f'&#9881; {tools_str}</span>'
    ) if tools_str else ""

    components.html(f"""
<script>
(function() {{
  var doc = window.parent.document;

  var old = doc.getElementById('hg-judge');
  if (old) old.remove();

  function inject() {{
    var stBot = doc.querySelector('[data-testid="stBottom"]');
    if (!stBot) {{ setTimeout(inject, 200); return; }}

    var bar = doc.createElement('div');
    bar.id = 'hg-judge';
    bar.style.cssText =
      'display:flex;align-items:center;gap:8px;' +
      'padding:5px 18px 5px 14px;font-family:monospace;' +
      'font-size:11px;line-height:1.3;' +
      'background:linear-gradient(90deg,rgba(60,4,4,0.97) 0%,rgba(30,2,2,0.97) 100%);' +
      'border-top:1px solid rgba(139,0,0,0.45);' +
      'border-bottom:1px solid rgba(80,0,0,0.3);';

    bar.innerHTML =
      '<span style="font-size:16px;flex-shrink:0">{icon}</span>' +
      '<span style="color:{color};font-weight:bold;letter-spacing:1.5px;' +
             'font-size:10px;flex-shrink:0;text-shadow:0 0 6px {color}">{label}</span>' +
      '<span style="color:rgba(139,0,0,0.6);flex-shrink:0;margin:0 2px">|</span>' +
      '<span style="color:rgba(200,80,80,0.85);flex-shrink:0">' +
        'Confiance : <b style="color:{color}">{conf_pct} %</b>' +
      '</span>' +
      '{tools_html}' +
      '<span style="color:rgba(139,0,0,0.6);flex-shrink:0;margin:0 2px">|</span>' +
      '<span style="color:rgba(170,90,90,0.80);font-style:italic;' +
             'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1">' +
        '{reasoning}' +
      '</span>';

    stBot.appendChild(bar);
  }}

  inject();
}})();
</script>
""", height=0)


# ── App ───────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="HorRAGor BOT",
    page_icon="🩸",
    layout="centered",
)

_inject_background()

st.title("🩸 HorRAGor BOT")
st.caption("Ton guide dans l'univers de l'horreur — cinéma, littérature, jeux vidéo.")

if "messages" not in st.session_state:
    st.session_state.messages = []

if "last_verdict" not in st.session_state:
    st.session_state.last_verdict = None

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Murmure ton sort dans l'obscurité..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("HorRAGor réfléchit..."):
            try:
                # Historique = messages précédents (hors question courante),
                # limité aux 8 derniers pour maîtriser la taille du contexte.
                history = [
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.messages[:-1]
                ][-8:]
                response = _authenticated_post(
                    API_URL,
                    json={"question": prompt, "history": history},
                    timeout=60.0,
                )
                response.raise_for_status()
                data   = response.json()
                answer = data.get("answer", "Pas de réponse reçue.")
                st.session_state.last_verdict    = data.get("judge_verdict")
                st.session_state.last_tools_used = data.get("tools_used", [])
            except httpx.ConnectError:
                answer = "Impossible de joindre le serveur. Vérifie que l'API FastAPI est lancée."
                st.session_state.last_verdict = None
            except httpx.HTTPStatusError as e:
                answer = f"Erreur serveur ({e.response.status_code})."
                st.session_state.last_verdict = None
            except Exception as e:
                answer = f"Erreur inattendue : {e}"
                st.session_state.last_verdict = None

        answer = _sanitize_markdown(answer)
        st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})
    _inject_judge_verdict(st.session_state.last_verdict, st.session_state.get("last_tools_used"))
