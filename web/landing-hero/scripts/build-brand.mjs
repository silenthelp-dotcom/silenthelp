import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {Resvg} from '@resvg/resvg-js';
const root=fileURLToPath(new URL('../../../',import.meta.url));
const paths=JSON.parse(await readFile(path.join(root,'web/landing-hero/logo-paths.json'),'utf8'));
const strokes=paths.map(d=>`<path fill="#111" d="${d}"/>`).join('');
const mark=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" role="img" aria-label="SilentHelp SH brain"><rect width="1024" height="1024" rx="180" fill="white"/><g transform="translate(80 160) scale(.304) translate(-760 -600)">${strokes}</g></svg>`;
const template=mark.replace(/<rect[^>]*\/>/,'');
const original=await readFile(path.join(root,'static/cinematic/img/silenthelp-sh.svg'),'utf8');
const full=original.replace(/(<svg[^>]*>)/,'$1<rect width="4358" height="4358" fill="white"/>');
const png=(svg,size)=>new Resvg(svg,{fitTo:{mode:'width',value:size}}).render().asPng();
const save=(p,data)=>writeFile(path.join(root,p),data);
await mkdir(path.join(root,'static/brand'),{recursive:true});
await save('static/brand/mark.svg',mark);await save('static/brand/logo.svg',full);
for(const size of [32,48,64,96,128,180,256,512])await save(`static/img/badge-${size}.png`,png(mark,size));
await save('static/img/badge.png',png(mark,1880));await save('static/img/logo-full.png',png(full,1024));
for(const size of [32,128])await save(`static/cinematic/img/badge-${size}.png`,png(mark,size));
for(const name of ['logo-face.png','logo-1024.png'])await save(`static/cinematic/img/${name}`,png(full,1024));
for(const dest of ['hq/frontend/public/favicon.svg','static/hq1/favicon.svg'])await save(dest,mark);
for(const [name,size] of [['menubar.png',20],['menubar@2x.png',40],['menubar@3x.png',60]])await save(`SilentHelpAgent/${name}`,png(template,size));
// ICNS uses PNG-backed representations; the existing macOS build bundles this file.
const chunks=[];for(const [type,size] of [['icp4',16],['icp5',32],['icp6',64],['ic07',128],['ic08',256],['ic09',512],['ic10',1024]]){const data=png(mark,size),head=Buffer.alloc(8);head.write(type);head.writeUInt32BE(data.length+8,4);chunks.push(head,data)}
const head=Buffer.alloc(8);head.write('icns');head.writeUInt32BE(8+chunks.reduce((n,b)=>n+b.length,0),4);await save('SilentHelpAgent/AppIcon.icns',Buffer.concat([head,...chunks]));
console.log('Rendered SH logo assets for the website, web app, favicons, and native app sources.');
