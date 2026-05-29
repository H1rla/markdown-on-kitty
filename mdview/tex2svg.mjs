// tex2svg.mjs — TeX 数式を MathJax v3 で SVG 文字列に変換して stdout へ出力する。
//
// mdview の外部数式レンダラ。Node.js と mathjax-full が必要:
//     npm install -g mathjax-full
//   （または mdview ディレクトリで npm install mathjax-full）
//
// 使い方:
//     node tex2svg.mjs '<tex>' <display(0|1)>
import { mathjax } from 'mathjax-full/js/mathjax.js';
import { TeX } from 'mathjax-full/js/input/tex.js';
import { SVG } from 'mathjax-full/js/output/svg.js';
import { liteAdaptor } from 'mathjax-full/js/adaptors/liteAdaptor.js';
import { RegisterHTMLHandler } from 'mathjax-full/js/handlers/html.js';
import { AllPackages } from 'mathjax-full/js/input/tex/AllPackages.js';

const adaptor = liteAdaptor();
RegisterHTMLHandler(adaptor);

const tex = new TeX({ packages: AllPackages });
const svg = new SVG({ fontCache: 'local' });
const doc = mathjax.document('', { InputJax: tex, OutputJax: svg });

const src = process.argv[2] || '';
const display = process.argv[3] === '1';
const node = doc.convert(src, { display });
process.stdout.write(adaptor.outerHTML(node));
