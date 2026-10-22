// 도입 슬라이드 — "질문만이 아니라 액션까지"
import { chromium } from '../video2/lib.mjs';
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1.5 });
await p.setContent(`<!doctype html><meta charset="utf-8"><style>
 html,body{margin:0;width:1280px;height:720px;background:#0b1018;color:#e8eef5;font-family:-apple-system,'Apple SD Gothic Neo',sans-serif}
 .w{padding:120px 110px}.k{font-size:20px;color:#7aa7d6;letter-spacing:.1em}
 h1{font-size:54px;line-height:1.35;margin:26px 0 40px;font-weight:800}h1 b{color:#ffb454}
 .row{display:flex;gap:16px;align-items:center;font-size:24px;color:#cfdbe8}
 .c{border:1px solid #2b3a50;border-radius:999px;padding:10px 22px;background:#121a26}.a{color:#ffb454}</style>
 <div class="w"><div class="k">ONTOLOGY STUDIO · 키네틱 액션</div>
 <h1>온톨로지에 질문만 하는 게 아니라,<br><b>액션까지</b> 시킬 수 있다면?</h1>
 <div class="row"><span class="c">질의</span><span class="a">→</span><span class="c">커맨드</span><span class="a">→</span><span class="c">승인</span><span class="a">→</span><span class="c">실행</span><span class="a">→</span><span class="c">되돌리기</span></div></div>`);
await p.screenshot({ path: 'slides/h00-hook.png' });
await b.close();
