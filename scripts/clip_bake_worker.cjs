/* Vector-only Skia PathKit backend. Reads one JSON request per stdin line. */
'use strict';
const readline = require('readline');
const nodePath = require('path');
const canvasPath = process.env.PPT_COMPAT_CANVAS_MODULE ||
  (process.env.RUNTIME_NODE_MODULES ? nodePath.join(process.env.RUNTIME_NODE_MODULES, '@napi-rs/canvas') : '@napi-rs/canvas');
let canvas;
try { canvas = require(canvasPath); }
catch (e) { throw new Error('Install @napi-rs/canvas, or set PPT_COMPAT_CANVAS_MODULE / RUNTIME_NODE_MODULES. '+e.message); }
const {Path2D, PathOp, StrokeCap, StrokeJoin, FillType} = canvas;

function path(d, rule='nonzero') {
  const p = new Path2D(d || '');
  p.setFillType(rule === 'evenodd' ? FillType.EvenOdd : FillType.Winding);
  return p;
}
function serialize(p) {
  // Skia boolean results are normally evenodd. Explicit winding conversion is
  // required before handing the bare SVG d to a native PowerPoint custom path.
  return p.asWinding().toSVGString();
}
function run(r) {
  if (r.op === 'intersect') {
    return serialize(path(r.subject_d, r.fill_rule).op(path(r.clip_d, r.clip_rule), PathOp.Intersect));
  }
  if (r.op === 'union' || r.op === 'difference') {
    return serialize(path(r.subject_d).op(path(r.clip_d), r.op === 'union' ? PathOp.Union : PathOp.Difference));
  }
  if (r.op === 'stroke') {
    if (!(r.width > 0)) return '';
    let p = path(r.d);
    if (r.dash && r.dash.length) {
      const dash = r.dash.length === 1 ? [r.dash[0], r.dash[0]] : r.dash;
      if (dash.length !== 2 || dash.some(v => !(v >= 0)) || dash.every(v => v === 0)) {
        throw new Error('This backend accepts one on/off dash pair; longer SVG dash patterns are not silently approximated.');
      }
      p = p.dash(dash[0], dash[1], r.dash_offset || 0);
    }
    const cap = {butt: StrokeCap.Butt, round: StrokeCap.Round, square: StrokeCap.Square}[r.cap || 'butt'];
    const join = {miter: StrokeJoin.Miter, round: StrokeJoin.Round, bevel: StrokeJoin.Bevel}[r.join || 'miter'];
    if (cap === undefined || join === undefined) throw new Error('Unsupported cap or join');
    return serialize(p.stroke({width:r.width, cap, join, miterLimit:r.miter_limit || 4}));
  }
  if (r.op === 'bounds') return path(r.d).computeTightBounds();
  if (r.op === 'normalize') return serialize(path(r.d, r.fill_rule));
  if (r.op === 'ping') return {backend:'@napi-rs/canvas Skia PathKit', vectorOnly:true};
  throw new Error(`Unknown operation ${r.op}`);
}
const rl = readline.createInterface({input:process.stdin, crlfDelay:Infinity});
rl.on('line', line => {
  try { process.stdout.write(JSON.stringify({ok:true, value:run(JSON.parse(line))})+'\n'); }
  catch (e) { process.stdout.write(JSON.stringify({ok:false, error:String(e.stack || e)})+'\n'); }
});
