#!/usr/bin/env node
/**
 * Create an artifact-tool-authored candidate text base for build_native_pptx.py.
 * This handles the controlled redraw's single-line text records, not arbitrary
 * SVG/PDF text layout. Native baseline/opacity correction occurs in the Python
 * postprocessor. Final delivery still requires the presentations skill's
 * finalizer, font/integrity checks and rendered visual inspection.
 *
 * node build_native_base.mjs --texts texts.json --svg artwork.svg --output base.pptx
 * Alternative canvas: --width 1200 --height 900 instead of --svg.
 * RUNTIME_NODE_MODULES may point to a bundled node_modules directory.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

const USAGE = 'Usage: build_native_base.mjs --texts FILE (--svg FILE | --width N --height N) --output FILE [--baseline-factor 0.91]';
const require = createRequire(import.meta.url);
async function loadArtifactTool() {
  try { return await import('@oai/artifact-tool'); }
  catch (original) {
    const roots = (process.env.RUNTIME_NODE_MODULES || '').split(path.delimiter).filter(Boolean);
    for (const root of roots) {
      try {
        const entry = require.resolve('@oai/artifact-tool', { paths: [root, path.dirname(root)] });
        return await import(pathToFileURL(entry).href);
      } catch { /* Try another explicitly configured runtime root. */ }
    }
    throw new Error('Cannot load @oai/artifact-tool. Install/resolve it normally or set RUNTIME_NODE_MODULES to the bundled node_modules directory. '+original.message);
  }
}
function args(argv) {
  const out = {};
  const keys = new Set(['texts','svg','width','height','output','baseline-factor']);
  for (let i=0; i<argv.length; i++) {
    if (argv[i]==='--help') { console.log(USAGE); process.exit(0); }
    if (!argv[i].startsWith('--') || !keys.has(argv[i].slice(2)) || i+1>=argv.length || argv[i+1].startsWith('--')) throw new Error(USAGE);
    const key=argv[i].slice(2); if(key in out) throw new Error('Duplicate argument: '+key);
    out[key]=argv[++i];
  }
  if (!out.texts || !out.output || (!out.svg && (!out.width || !out.height))) throw new Error(USAGE);
  if(out.svg && (out.width || out.height)) throw new Error('Choose --svg OR --width/--height, not both.');
  return out;
}
function finite(v,name) { if(typeof v!=='number' || !Number.isFinite(v)) throw new Error(name+' must be a finite number.'); return v; }
function validate(items) {
  if(!Array.isArray(items)) throw new Error('texts.json must contain an array.');
  const ids=new Set();
  for(const t of items) {
    if(typeof t.id!=='string'||!t.id||ids.has(t.id)) throw new Error('Text ids must be nonempty and unique.');ids.add(t.id);
    if(typeof t.text!=='string'||/[\r\n]/.test(t.text)) throw new Error(t.id+': only single-line text is supported.');
    for(const k of ['x','baseline','font_size']) finite(t[k],t.id+'.'+k);
    if(t.font_size<=0||typeof t.font_family!=='string'||!t.font_family||typeof t.bold!=='boolean') throw new Error(t.id+': invalid explicit font fields.');
    if(!/^#[0-9a-fA-F]{6}$/.test(t.color)) throw new Error(t.id+': color must be #RRGGBB.');
    if(!['start','middle','end'].includes(t.text_anchor??'start')) throw new Error(t.id+': unsupported text_anchor.');
    const runs=t.runs??[{text:t.text,font_size:t.font_size,font_family:t.font_family,bold:t.bold,color:t.color,opacity:t.opacity??1,baseline_shift:'baseline'}];
    if(!Array.isArray(runs)||!runs.length||runs.map(r=>r.text).join('')!==t.text) throw new Error(t.id+': runs must concatenate exactly to text.');
    for(const r of runs) {
      if(typeof r.text!=='string'||/[\r\n]/.test(r.text)) throw new Error(t.id+': only single-line runs are supported.');
      finite(r.font_size,t.id+'.run.font_size');if(r.font_size<=0)throw new Error('Run font_size must be positive.');
      if(!['baseline','sub','super'].includes(r.baseline_shift??'baseline')) throw new Error(t.id+': unsupported baseline shift.');
      for(const k of ['x','y','dx','dy','rotate']) if(k in r) throw new Error(t.id+': positioned/rotated runs must be handled explicitly, not flattened silently.');
      if(r.opacity!==undefined && (finite(r.opacity,'run.opacity')<0 || r.opacity>1)) throw new Error('run.opacity must be in [0,1].');
    }
    t._runs=runs;
  }
}
async function main() {
  const opt=args(process.argv.slice(2));
  if([opt.texts,opt.svg].filter(Boolean).some(p=>path.resolve(p)===path.resolve(opt.output)))throw new Error('Output must differ from every input file.');
  let vx=0,vy=0,width,height;
  if(opt.svg) {
    const xml=await fs.readFile(opt.svg,'utf8');
    const root=xml.match(/<svg\b[^>]*>/s)?.[0];
    if(!root)throw new Error('SVG root not found.');
    const vb=root.match(/\bviewBox\s*=\s*["']([^"']+)["']/)?.[1];
    if(!vb)throw new Error('Controlled SVG input requires an explicit viewBox.');
    const nums=vb.trim().split(/[\s,]+/).map(Number);
    if(nums.length!==4||nums.some(v=>!Number.isFinite(v)))throw new Error('Invalid SVG viewBox.');
    [vx,vy,width,height]=nums;
  } else { width=Number(opt.width);height=Number(opt.height); }
  if(!(width>0&&height>0&&Number.isFinite(width)&&Number.isFinite(height))) throw new Error('Canvas width and height must be positive finite numbers.');
  const baselineFactor=Number(opt['baseline-factor']??'.91');
  if(!(baselineFactor>0&&baselineFactor<2))throw new Error('baseline-factor must be between 0 and 2.');
  const items=JSON.parse(await fs.readFile(opt.texts,'utf8'));validate(items);
  const {Presentation,PresentationFile}=await loadArtifactTool();
  const p=Presentation.create({slideSize:{width,height}});
  const s=p.slides.add();s.background.fill='#FFFFFF';
  for(const t of items) {
    const anchor=t.text_anchor??'start';
    const estimate=Math.max(30,t._runs.reduce((n,r)=>n+[...r.text].length*r.font_size*.73,0));
    const tx=t.x-vx, baseline=t.baseline-vy;
    let boxWidth, left, alignment;
    if(anchor==='start'){left=tx;boxWidth=Math.min(width-tx,estimate);alignment='left';}
    else if(anchor==='middle'){boxWidth=Math.min(estimate,2*Math.min(tx,width-tx));left=tx-boxWidth/2;alignment='center';}
    else {boxWidth=Math.min(tx,estimate);left=tx-boxWidth;alignment='right';}
    if(!(boxWidth>0))throw new Error(t.id+': text anchor is outside the canvas.');
    const maxFont=Math.max(t.font_size,...t._runs.map(r=>r.font_size));
    const sh=s.shapes.add({name:t.id,geometry:'textbox',position:{left,top:baseline-t.font_size*baselineFactor,width:boxWidth,height:maxFont*1.7},fill:'none',line:{fill:'none',width:0}});
    sh.text.style={typeface:t.font_family,fontSize:t.font_size,bold:t.bold,color:t.color,autoFit:'none',wrap:'none',alignment,verticalAlignment:'top',insets:{left:0,right:0,top:0,bottom:0}};
    sh.text.set([{runs:t._runs.map(r=>({run:r.text,textStyle:{fontSize:`${r.font_size}px`,typeface:r.font_family??t.font_family,bold:r.bold??t.bold,color:r.color??t.color}}))}]);
  }
  s.speakerNotes.textFrame.setText('Candidate native text base for a controlled SVG redraw. Native geometry, run baseline shifts and opacity are applied by build_native_pptx.py. Render and inspect the completed candidate, then run the presentations skill finalizer before delivery.');
  await fs.mkdir(path.dirname(path.resolve(opt.output)),{recursive:true});
  await (await PresentationFile.exportPptx(p)).save(opt.output);
  console.log(JSON.stringify({output:path.resolve(opt.output),status:'candidate_text_base',text_boxes:items.length,width,height,baseline_factor:baselineFactor,requires_native_postprocessor:true},null,2));
}
main().catch(e=>{console.error('ERROR:',e.message);process.exitCode=1;});
