export function containsTile(parent,child) {
  const [z,x,y]=parent.split('/').map(Number),[cz,cx,cy]=child.split('/').map(Number);
  return z<=cz&&Math.floor(cx/2**(cz-z))===x&&Math.floor(cy/2**(cz-z))===y;
}
export function visibleLoadedTiles(desired,loaded) {
  const selected=new Set();
  function ancestors(key) {
    let [z,x,y]=key.split('/').map(Number);const result=[];
    while(z>0){z--;x=Math.floor(x/2);y=Math.floor(y/2);result.push(`${z}/${x}/${y}`);}
    return result;
  }
  let descendants;
  for(const key of desired) {
    if(loaded.has(key)){selected.add(key);continue;}
    const parent=ancestors(key).find(candidate=>loaded.has(candidate));
    if(parent)selected.add(parent);
    else {
      if(!descendants){descendants=new Map();for(const candidate of loaded)for(const ancestor of ancestors(candidate)){if(!descendants.has(ancestor))descendants.set(ancestor,[]);descendants.get(ancestor).push(candidate);}}
      for(const candidate of descendants.get(key)??[])selected.add(candidate);
    }
  }
  return new Set([...selected].filter(key=>!ancestors(key).some(parent=>selected.has(parent))));
}
