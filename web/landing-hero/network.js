// Seeded, bounded construction keeps the network stable through resizes.
export function createNetwork(contains,count=180){
 let seed=81;const random=()=>{seed=seed*16807%2147483647;return(seed-1)/2147483646};
 const nodes=[];
 for(let attempts=0;nodes.length<count&&attempts<count*120;attempts++){
  const x=18+random()*564,y=10+random()*466;
  if(!contains(x,y))continue;
  nodes.push({x,y,color:nodes.length%2?'80,139,255':'255,65,86',branches:Array.from({length:4},()=>({angle:random()*Math.PI*2,length:9+random()*20}))});
 }
 const edges=[];nodes.forEach((node,i)=>nodes.map((other,j)=>({j,d:Math.hypot(node.x-other.x,node.y-other.y)})).filter(v=>v.j>i&&v.d<85).sort((a,b)=>a.d-b.d).slice(0,3).forEach(({j})=>edges.push({a:i,b:j,phase:random()})));
 return {nodes,edges};
}
export const proximity=(node,pointer,radius)=>Math.max(0,1-Math.hypot(node.x-pointer.x,node.y-pointer.y)/radius);
