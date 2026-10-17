/* Editable, grid-aligned SVG UI assets. No third-party icon library. */
const fs=require('node:fs'),path=require('node:path'),sharp=require('sharp');
const root=path.resolve(__dirname,'..');const out=p=>path.join(root,p);
const C={ink:'#211B32',cream:'#F7EDCF',coral:'#F26F73',teal:'#62B6BB',green:'#5F9E71',yellow:'#F6CB45',red:'#E85167',orange:'#DE8852',blue:'#77A9C0',muted:'#AD9FAD'};
const r=(x,y,w,h,c='ink')=>`<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${C[c]||c}"/>`;
const p=(d,c='ink')=>`<path d="${d}" fill="${C[c]||c}"/>`;
const rectIcon=(color)=>r(3,3,18,18)+r(5,5,14,14,color);
const a={};
a['house']=p('M2 10H4V8H6V6H8V4H10V2H14V4H16V6H18V8H20V10H22V13H20V22H4V13H2Z')+p('M5 11H7V9H9V7H11V5H13V7H15V9H17V11H19V12H17V20H7V12H5Z','green')+r(10,13,4,7,'cream')+r(16,3,3,5);
a['car']=p('M1 12H4V8H6V5H18V8H20V12H23V19H21V22H17V19H7V22H3V19H1Z')+p('M4 13H6V9H18V13H21V17H3V13Z','blue')+r(7,7,10,4,'teal')+r(11,7,2,5)+r(3,14,3,2,'cream')+r(18,14,3,2,'cream')+r(4,18,2,2,'muted')+r(18,18,2,2,'muted');
a['coin-stack']=r(3,9,8,13)+r(1,12,12,7)+r(4,10,6,11,'orange')+r(2,13,10,3,'yellow')+r(13,4,8,18)+r(11,7,12,11)+r(14,5,6,16,'orange')+r(12,8,10,3,'yellow')+r(12,14,10,3,'yellow')+r(15,6,2,14,'cream');
a['heart']=p('M1 5H3V3H9V5H11V7H13V5H15V3H21V5H23V13H21V15H19V17H17V19H15V21H9V19H7V17H5V15H3V13H1Z','coral')+r(4,6,4,2,'cream');
a['receipt']=p('M4 2H18V4H20V22H17V20H15V22H12V20H10V22H7V20H4Z')+r(6,4,10,15,'cream')+r(16,6,2,13,'cream')+r(8,7,6,2,'coral')+r(8,11,8,1)+r(8,14,8,1)+r(8,17,4,1);
a['question']=p('M6 1H18V3H21V6H23V18H21V21H18V23H6V21H3V18H1V6H3V3H6Z')+p('M7 3H17V5H19V7H21V17H19V19H17V21H7V19H5V17H3V7H5V5H7Z','red')+p('M8 6H16V8H18V12H16V14H13V16H10V12H13V10H15V8H10V10H7V8H8Z','cream')+r(10,18,3,2,'cream');
a['arrow-left']=p('M15 3H11V5H9V7H7V9H5V15H7V17H9V19H11V21H15Z');
a['arrow-right']=p('M9 3H13V5H15V7H17V9H19V15H17V17H15V19H13V21H9Z');
a['chevron-down']=p('M3 7H7V9H9V11H11V13H13V11H15V9H17V7H21V11H19V13H17V15H15V17H9V15H7V13H5V11H3Z');
a['search']=p('M5 2H13V4H16V7H18V13H16V16H18V18H20V20H22V23H18V21H16V19H14V17H5V15H2V12H1V7H2V4H5Z')+p('M6 5H12V7H15V12H12V14H6V12H4V7H6Z','cream');
a['download']=r(10,2,4,11)+p('M4 10H8V12H10V14H14V12H16V10H20V14H18V16H16V18H8V16H6V14H4Z')+r(2,19,20,3)+r(2,16,3,4)+r(19,16,3,4);
a['swap']=p('M7 3H10V6H7V8H22V11H7V13H10V16H7V14H5V12H3V10H1V9H3V7H5V5H7Z')+p('M17 8H14V11H17V13H2V16H17V18H14V21H17V19H19V17H21V15H23V14H21V12H19V10H17Z');
a['chart']=r(2,13,5,9,'teal')+r(9,3,5,19,'teal')+r(16,9,5,13,'teal');
a['sushi']=p('M5 3H19V5H22V19H19V22H5V20H2V6H5Z')+r(5,5,14,14,'cream')+r(7,7,10,10)+r(9,9,6,6,'coral')+r(19,8,2,9,'red')+r(4,6,3,4,'coral');
a['grocery']=p('M1 3H6V6H22V9H20V17H8V15H6V8H4V6H1Z')+r(8,8,11,6,'blue')+r(9,18,4,4)+r(17,18,4,4)+r(11,9,2,4,'teal')+r(16,9,2,4,'teal');
a['petrol']=p('M5 2H15V4H17V7H19V9H21V12H23V21H19V19H18V15H16V22H2V19H4V4H5Z')+r(6,4,8,15,'red')+r(7,5,6,6,'cream')+r(6,19,8,1,'coral')+r(19,12,2,6,'orange');
a['calendar']=r(3,4,18,18)+r(5,9,14,11,'cream')+r(5,6,14,3,'coral')+r(6,1,3,6)+r(15,1,3,6)+r(7,12,3,3,'teal')+r(12,12,3,3,'teal')+r(7,16,3,2,'teal')+r(16,12,2,3,'teal');
a['weekday']=a.calendar;
a['weekend']=p('M9 1H15V4H18V7H21V16H18V19H15V22H9V19H6V16H3V7H6V4H9Z','yellow')+r(9,7,2,3)+r(14,7,2,3)+p('M8 13H10V15H14V13H16V16H14V18H10V16H8Z');
a['extra']=p('M10 1H14V7H17V10H23V14H17V17H14V23H10V17H7V14H1V10H7V7H10Z','yellow')+r(10,10,4,4,'cream');
a['paw']=r(2,5,5,7,'orange')+r(9,2,5,7,'orange')+r(17,5,5,7,'orange')+p('M7 12H17V14H20V21H17V22H7V21H4V14H7Z','orange')+r(9,16,6,3,'cream');
a['soap']=r(3,10,18,12)+r(5,12,14,8,'coral')+r(7,14,10,2,'cream')+r(3,4,4,4,'teal')+r(10,2,5,5,'blue')+r(18,5,3,3,'teal');
a['toll']=r(3,9,5,14)+r(2,5,20,4)+r(5,6,4,2,'coral')+r(13,6,4,2,'coral')+r(19,9,3,14,'blue')+r(4,10,3,3,'yellow')+r(9,19,9,2,'muted');
a['parents']=r(4,3,6,6,'orange')+r(14,3,6,6,'orange')+r(2,11,10,10,'green')+r(12,11,10,10,'teal')+r(5,3,4,2,'muted')+r(15,3,4,2,'muted')+r(5,21,3,2)+r(16,21,3,2);
a['check']=p('M2 11H6V14H9V17H12V14H15V11H18V8H21V4H24V10H21V13H18V16H15V19H12V22H7V19H4V16H2Z','green');
a['clock']=p('M7 1H17V3H20V6H23V18H20V21H17V23H7V21H4V18H1V6H4V3H7Z')+p('M8 4H16V6H19V8H20V16H18V19H16V20H8V18H5V16H4V8H6V5H8Z','cream')+r(10,6,3,8)+r(12,11,5,3);
a['close']=p('M3 3H7V7H11V10H13V7H17V3H21V7H17V11H14V13H17V17H21V21H17V17H13V14H11V17H7V21H3V17H7V13H10V11H7V7H3Z');
a['filter']=p('M2 3H22V7H20V9H18V11H16V13H14V21H10V13H8V11H6V9H4V7H2Z');
a['plus']=r(10,3,4,18)+r(3,10,18,4);
a['medal']=p('M7 1H17V3H20V6H23V18H20V21H17V23H7V21H4V18H1V6H4V3H7Z')+p('M8 3H16V5H19V7H21V17H19V19H16V21H8V19H5V17H3V7H5V5H8Z','yellow');
a['empty-wallet']=r(2,5,19,16)+r(4,7,15,12,'orange')+r(14,10,9,7)+r(16,12,5,3,'yellow')+r(4,3,14,3)+r(6,4,10,2,'cream');
function svg(body,w=24,h=24){return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" shape-rendering="crispEdges">${body}</svg>\n`;}
async function main(){
 const manifest=[];
 for(const [name,body]of Object.entries(a)){
  const s=svg(body);fs.writeFileSync(out(`assets/icons/${name}.svg`),s);
  await sharp(Buffer.from(s)).resize(48,48,{kernel:'nearest'}).png().toFile(out(`assets/icons/${name}@2x.png`));
  manifest.push({id:name,svg:`assets/icons/${name}.svg`,png2x:`assets/icons/${name}@2x.png`,viewBox:'0 0 24 24',size:24});
 }
 fs.writeFileSync(out('assets/icons/icons.svg'),`<svg xmlns="http://www.w3.org/2000/svg" shape-rendering="crispEdges">${Object.entries(a).map(([name,body])=>`<symbol id="${name}" viewBox="0 0 24 24">${body}</symbol>`).join('')}</svg>\n`);
 fs.writeFileSync(out('assets/icons/icon-manifest.json'),JSON.stringify(manifest,null,2)+'\n');
 const letters={D:['11110','11011','11001','11001','11001','11011','11110'],U:['11011','11011','11011','11011','11011','11011','01110'],I:['11111','00100','00100','00100','00100','00100','11111'],T:['11111','11111','00100','00100','00100','00100','00100']};
 for(const [variant,color]of [['cream',C.cream],['ink',C.ink]]){
  let body='';[...'DUIT'].forEach((letter,i)=>letters[letter].forEach((row,y)=>[...row].forEach((v,x)=>{if(v==='1')body+=r(i*6+x,y,1,1,color)})));
  fs.writeFileSync(out(`assets/brand/duit-${variant}.svg`),svg(body,23,7));
  await sharp(Buffer.from(svg(body,23,7))).resize(230,70,{kernel:'nearest'}).png().toFile(out(`assets/brand/duit-${variant}@10x.png`));
 }
 const fav=svg(r(0,0,32,32)+r(6,5,14,3,'cream')+r(6,8,4,16,'cream')+r(20,8,5,16,'cream')+r(6,24,14,3,'cream'),32,32);
 fs.writeFileSync(out('assets/brand/favicon.svg'),fav);
 await sharp(Buffer.from(fav)).png().toFile(out('assets/brand/favicon-32.png'));
 const tile=svg(r(0,0,8,8)+r(0,0,1,1,'#292139')+r(4,4,1,1,'#292139'),8,8);
 fs.writeFileSync(out('assets/scene/plum-dither.svg'),tile);
 console.log(Object.keys(a).length,'SVG icons with 2x PNG copies, brand assets and background tile exported.');
}
main().catch(e=>{console.error(e);process.exit(1)});
