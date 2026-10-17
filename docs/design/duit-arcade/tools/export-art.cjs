/* Technical export only: keep generated sources unchanged, isolate alpha, slice,
 * align on a shared baseline and resize with nearest-neighbor. Node + sharp. */
const fs = require('node:fs');
const path = require('node:path');
const sharp = require('sharp');
const root = path.resolve(__dirname, '..');
const out = p => path.join(root, p);
const specs = [
  {id:'hanz',source:'source/hanz-generated.png',rows:2,states:['idle','wave'],durations:[4000,800]},
  {id:'vanisa',source:'source/vanisa-generated.png',rows:2,states:['idle','wave'],durations:[4400,800]},
  {id:'chuchu',source:'source/chuchu-generated.png',rows:3,rowCuts:[0,512,855,1254],states:['idle','walk','sleep'],durations:[4800,640,2400]}
];
function bounds(data,w,h,channels=4) {
  let left=w,top=h,right=-1,bottom=-1;
  for(let y=0;y<h;y++) for(let x=0;x<w;x++) if(data[(y*w+x)*channels+3]>=128) {
    left=Math.min(left,x); top=Math.min(top,y); right=Math.max(right,x);bottom=Math.max(bottom,y);
  }
  if(right<0) throw new Error('Empty frame');
  return {left,top,width:right-left+1,height:bottom-top+1};
}
function binaryAlpha(data) {
  for(let i=0;i<data.length;i+=4) {data[i+3]=data[i+3]>=128?255:0; if(!data[i+3]) data[i]=data[i+1]=data[i+2]=0;}
  return data;
}
async function main(){
 const manifest={version:'1.0.0',frameSize:{width:64,height:64},anchor:{x:32,y:60},pixelScale:'integer only: 1x or 2x',alpha:'binary 0 or 255',characters:{}};
 for(const spec of specs){
  const raw=await sharp(out(spec.source)).ensureAlpha().raw().toBuffer({resolveWithObject:true});
  const w=raw.info.width,h=raw.info.height; const frames=[];
  for(let row=0;row<spec.rows;row++)for(let col=0;col<4;col++){
    const x0=Math.round(col*w/4), x1=Math.round((col+1)*w/4);
    const y0=spec.rowCuts?spec.rowCuts[row]:Math.round(row*h/spec.rows),y1=spec.rowCuts?spec.rowCuts[row+1]:Math.round((row+1)*h/spec.rows);
    let crop=await sharp(raw.data,{raw:{width:w,height:h,channels:4}}).extract({left:x0,top:y0,width:x1-x0,height:y1-y0}).raw().toBuffer();
    binaryAlpha(crop); const b=bounds(crop,x1-x0,y1-y0);
    let footLeft=x1-x0,footRight=-1;
    const fy=b.top+b.height-Math.max(2,Math.round(b.height*.06));
    for(let y=fy;y<b.top+b.height;y++) for(let x=b.left;x<b.left+b.width;x++) if(crop[(y*(x1-x0)+x)*4+3]) {footLeft=Math.min(footLeft,x);footRight=Math.max(footRight,x);}
    const anchorX=spec.id==='chuchu'?b.left+b.width/2:(footLeft+footRight+1)/2;
    frames.push({row,col,crop,b,anchorX,width:x1-x0,height:y1-y0});
  }
  let scale=Math.min(56/Math.max(...frames.map(f=>f.b.height)),56/Math.max(...frames.map(f=>f.b.width)));
  const dest=`assets/sprites/${spec.id}`;fs.mkdirSync(out(dest),{recursive:true});
  const pieces=[];const records=[];
  for(const f of frames){
   const rw=Math.max(1,Math.round(f.b.width*scale)),rh=Math.max(1,Math.round(f.b.height*scale));
   const rx=Math.max(2,Math.min(62-rw,Math.round(32-(f.anchorX-f.b.left)*scale)));
   const ry=60-rh;
   const small=await sharp(f.crop,{raw:{width:f.width,height:f.height,channels:4}}).extract(f.b).resize(rw,rh,{kernel:'nearest'}).png().toBuffer();
   const png=await sharp({create:{width:64,height:64,channels:4,background:'#00000000'}}).composite([{input:small,left:rx,top:ry}]).png().toBuffer();
   const state=spec.states[f.row],name=`${state}-${String(f.col).padStart(2,'0')}.png`;
   fs.writeFileSync(out(`${dest}/${name}`),png);
   pieces.push({input:png,left:f.col*64,top:f.row*64});
   records.push({id:`${spec.id}.${state}.${f.col}`,state,index:f.col,x:f.col*64,y:f.row*64,w:64,h:64,anchor:{x:32,y:60},file:`${dest}/${name}`,visibleBounds:{x:rx,y:ry,w:rw,h:rh}});
  }
  const sheet=await sharp({create:{width:256,height:64*spec.rows,channels:4,background:'#00000000'}}).composite(pieces).png().toBuffer();
  fs.writeFileSync(out(`${dest}/${spec.id}-sheet.png`),sheet);
  await sharp(sheet).resize(512,128*spec.rows,{kernel:'nearest'}).png().toFile(out(`${dest}/${spec.id}-sheet@2x.png`));
  manifest.characters[spec.id]={sheet:`${dest}/${spec.id}-sheet.png`,sheet2x:`${dest}/${spec.id}-sheet@2x.png`,width:256,height:64*spec.rows,columns:4,rows:spec.rows,defaultFrame:`${dest}/idle-00.png`,animations:Object.fromEntries(spec.states.map((s,i)=>[s,{row:i,frames:[0,1,2,3],y:i*64,durationMs:spec.durations[i],loop:s!=='wave',timing:s==='idle'?'hold first 88%, then frames 1/2/3 for 2%/2%/8%':'equal steps(4)',facing:s==='walk'?'right':'front-or-rest'}])),frames:records};
  console.log(spec.id,records.length,'frames',256,64*spec.rows,'scale',scale.toFixed(4));
 }
 fs.writeFileSync(out('assets/sprites/sprite-manifest.json'),JSON.stringify(manifest,null,2)+'\n');
 const scene=await sharp(out('source/skyline-generated.png')).ensureAlpha().raw().toBuffer({resolveWithObject:true});
 binaryAlpha(scene.data);const b=bounds(scene.data,scene.info.width,scene.info.height);
 const trimmed=await sharp(scene.data,{raw:{width:scene.info.width,height:scene.info.height,channels:4}}).extract(b).resize({width:384,height:60,fit:'inside',kernel:'nearest'}).png().toBuffer();
 const md=await sharp(trimmed).metadata();
 await sharp({create:{width:384,height:64,channels:4,background:'#00000000'}}).composite([{input:trimmed,left:Math.floor((384-md.width)/2),top:60-md.height}]).png().toFile(out('assets/scene/skyline.png'));
 await sharp(out('assets/scene/skyline.png')).resize(768,128,{kernel:'nearest'}).png().toFile(out('assets/scene/skyline@2x.png'));
}
main().catch(e=>{console.error(e);process.exit(1)});
