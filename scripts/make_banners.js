/**
 * Render every banner from the same brand assets, so they cannot drift apart.
 *
 * Composed rather than generated. A banner has to hit an exact pixel size and keep its
 * content inside a safe area that differs per platform, X puts the avatar over the
 * lower-left, YouTube crops to 1546x423 on a TV and much wider on a desktop. An image model
 * cannot be told "and the wordmark must survive a centre crop", and it would redraw the mark
 * rather than use the one that ships.
 *
 *   node scripts/make_banners.js
 */
const fs = require('fs');
const path = require('path');
const { chromium } = require('/Users/rainmanjam/Documents/GitHub/calltab-io/node_modules/playwright-core');

const ROOT = path.resolve(__dirname, '..');
const BRAND = path.join(ROOT, 'docs/assets/brand');
const OUT = path.join(ROOT, 'docs/assets/banner');
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

const svg = f => fs.readFileSync(path.join(BRAND, f), 'utf8')
  .replace(/width="\d+" height="\d+"/, 'width="100%" height="100%"');

// The badge-less cut: a banner is already a surface, and the badged mark reads as a
// faint rectangle drawn around the tower on a near-black ground.
const MARK = svg('logo-bare.svg');

// Lifted from the slide deck (video/broll/broll.css), so the banners, the b-roll and the
// slides read as one thing when the video and the repository land together. The grid is a
// 96px substrate on a 1920 stage, 5% of the width, kept proportional here so its density
// looks identical at 1280 and at 2560 rather than dense on one and sparse on the other.
const INK = '#08090b';
const TEXT = '#f4f5f7';
const DIM = '#9aa1aa';
const FAINT = '#565d66';
const SANS = "'Geist',Inter,-apple-system,'Segoe UI',sans-serif";

/** The deck's grid substrate, masked so it fades at the edges, depth, not wallpaper.
 *
 *  The deck draws its lines at .030 alpha; these use .075. Not a drift: the deck is a
 *  1920px stage filling a screen, while a banner is usually met as a Slack unfurl or a
 *  profile header a few hundred pixels wide, where .030 disappears entirely and the grid
 *  reads as sensor noise rather than structure. Checked against .030/.045/.060/.075/.095/.120
 *  at banner scale: below .06 it vanishes, above .095 it turns into graph paper.
 */
const substrate = (w) => {
  const cell = Math.round(w * 0.05);
  const mask = 'radial-gradient(ellipse 78% 62% at 50% 46%, #000 35%, transparent 100%)';
  return `<div style="position:absolute;inset:0;pointer-events:none;
    background-image:
      linear-gradient(rgba(255,255,255,.075) 1px, transparent 1px),
      linear-gradient(90deg, rgba(255,255,255,.075) 1px, transparent 1px);
    background-size:${cell}px ${cell}px;
    -webkit-mask-image:${mask};mask-image:${mask}"></div>`;
};

// The severity ladder, in the tokens the findings themselves use.
const RUNGS = [
  ['#34d399', 'Control', 'the mistake is impossible'],
  ['#fbbf24', 'Warning', 'announced as it happens'],
  ['#ff4d4d', 'Detection', 'found afterwards'],
];

const ladder = (scale = 1) => RUNGS.map(([c, name, what]) => `
  <div style="display:flex;align-items:center;gap:${14 * scale}px">
    <div style="width:${13 * scale}px;height:${13 * scale}px;border-radius:${4 * scale}px;background:${c};flex:none"></div>
    <div style="font:600 ${17 * scale}px ${SANS};color:${TEXT};letter-spacing:-.02em">${name}</div>
    <div style="font:400 ${16 * scale}px ${SANS};color:${DIM}">${what}</div>
  </div>`).join('');

/** A frame with an optional safe-area box drawn for the proof sheet only. */
const page = (inner, w, h) => `<body style="margin:0;width:${w}px;height:${h}px;
  background:${INK};font-family:${SANS};overflow:hidden">
  <div style="position:absolute;inset:0;background:
    radial-gradient(${Math.round(w * 0.63)}px ${Math.round(h * 0.65)}px at 50% -10%,
      rgba(255,184,0,.045), transparent 62%)"></div>
  ${substrate(w)}
  ${inner}</body>`;

// The bare mark's viewBox hugs its ink and is taller than it is wide (48:97), so it is
// sized by HEIGHT and left to take its natural width. Handing it a square box would pad it
// back out with the empty space the tightened viewBox just removed.
const MARK_RATIO = 48 / 97;
const lockup = (markPx, namePx, gap) => `
  <div style="display:flex;align-items:center;gap:${gap}px">
    <div style="width:${Math.round(markPx * MARK_RATIO)}px;height:${markPx}px;flex:none">${MARK}</div>
    <div style="font-size:${namePx}px;font-weight:660;letter-spacing:-.042em;color:${TEXT}">poka-yoke</div>
  </div>`;

const BANNERS = {
  // Centre-safe: Slack, X and Discord all crop the edges of an OG image differently.
  'github-social.png': { w: 1280, h: 640, html: `
    <div style="position:relative;height:100%;display:flex;flex-direction:column;
                align-items:center;justify-content:center;gap:34px;padding:0 120px;text-align:center">
      ${lockup(112, 76, 30)}
      <div style="font-size:31px;line-height:1.4;color:${DIM};letter-spacing:-.012em;max-width:820px">
        Mistake-proofing for software. Audit code for what is easy to get wrong,
        design interfaces misuse cannot express, and turn incidents into devices.
      </div>
      <div style="display:flex;gap:38px;margin-top:6px">${RUNGS.map(([c, n]) => `
        <div style="display:flex;align-items:center;gap:11px">
          <div style="width:13px;height:13px;border-radius:4px;background:${c}"></div>
          <div style="font-size:19px;font-weight:600;color:${TEXT};letter-spacing:-.02em">${n}</div></div>`).join('')}</div>
    </div>` },

  // The avatar sits over the lower-left, so nothing important goes there.
  'x-header.png': { w: 1500, h: 500, html: `
    <div style="position:relative;height:100%;display:flex;align-items:center;
                justify-content:flex-end;padding:0 96px 0 430px">
      <div style="display:flex;flex-direction:column;gap:26px;align-items:flex-start">
        ${lockup(88, 60, 24)}
        <div style="font-size:25px;color:${DIM};letter-spacing:-.012em;max-width:760px;line-height:1.45">
          Shigeo Shingo's method, applied to code, process, interfaces and AI agents.
        </div>
        <div style="display:flex;flex-direction:column;gap:11px">${ladder(0.95)}</div>
      </div>
    </div>` },

  // 2560x1440 with a 1546x423 centre-safe area, everything that matters lives inside it.
  'youtube-channel.png': { w: 2560, h: 1440, html: `
    <div style="position:relative;height:100%;display:flex;align-items:center;justify-content:center">
      <div style="width:1546px;height:423px;display:flex;flex-direction:column;
                  align-items:center;justify-content:center;gap:30px;text-align:center">
        ${lockup(124, 84, 32)}
        <div style="font-size:33px;color:${DIM};letter-spacing:-.012em;max-width:1080px;line-height:1.4">
          Every feature you ship adds new ways to get it wrong. Poka-yoke removes them as you build.
        </div>
        <div style="display:flex;gap:44px;margin-top:4px">${RUNGS.map(([c, n]) => `
          <div style="display:flex;align-items:center;gap:12px">
            <div style="width:15px;height:15px;border-radius:5px;background:${c}"></div>
            <div style="font-size:21px;font-weight:600;color:${TEXT};letter-spacing:-.02em">${n}</div></div>`).join('')}</div>
      </div>
    </div>` },

  // Rendered inline at the top of the README, on either GitHub theme, hence its own ground.
  'readme-header.png': { w: 1200, h: 300, html: `
    <div style="position:relative;height:100%;display:flex;align-items:center;
                justify-content:space-between;padding:0 68px">
      <div style="display:flex;flex-direction:column;gap:18px">
        ${lockup(78, 54, 22)}
        <div style="font-size:21px;color:${DIM};letter-spacing:-.012em">Make the mistake impossible.</div>
      </div>
      <div style="display:flex;flex-direction:column;gap:13px">${ladder(0.92)}</div>
    </div>` },
};

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ executablePath: CHROME });
  for (const [name, { w, h, html }] of Object.entries(BANNERS)) {
    const p = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
    await p.setContent(page(html, w, h));
    await p.screenshot({ path: path.join(OUT, name) });
    await p.close();
    console.log(`  ${name.padEnd(24)} ${w}x${h}`);
  }
  await browser.close();
})();

/**
 * Proof sheet: every banner with its crops drawn on top.
 *
 * A banner is not "done" when it renders. It is done when it survives what each platform
 * does to it. YouTube shows 1546x423 on a phone, a wide band on desktop and the whole frame
 * only on a TV; X drops the avatar over the lower-left; an OG image gets centre-cropped by
 * some clients. Guessing at that is how a wordmark ends up half behind an avatar.
 */
const CROPS = {
  'youtube-channel.png': [
    { x: 507, y: 508, w: 1546, h: 423, label: 'mobile / TV-safe 1546x423' },
    { x: 128, y: 508, w: 2304, h: 423, label: 'desktop ~2304x423' },
  ],
  'x-header.png': [
    { x: 40, y: 320, w: 200, h: 200, label: 'avatar', round: true },
  ],
  'github-social.png': [
    { x: 160, y: 0, w: 960, h: 640, label: 'centre crop (some clients)' },
  ],
  'readme-header.png': [],
};
