export function tileOutlinePositions(data, fallbackHeight, offset) {
  const [west,south,east,north]=data.bounds;
  if(!data.terrain)return [west,south,fallbackHeight+offset,east,south,fallbackHeight+offset,east,north,fallbackHeight+offset,west,north,fallbackHeight+offset,west,south,fallbackHeight+offset];
  const {size,latitudes,heights_m}=data.terrain;
  const border=[];
  for(let col=0;col<size;col++)border.push(col);
  for(let row=1;row<size;row++)border.push(row*size+size-1);
  for(let col=size-2;col>=0;col--)border.push((size-1)*size+col);
  for(let row=size-2;row>0;row--)border.push(row*size);
  border.push(border[0]);
  return border.flatMap(index=>[west+(east-west)*(index%size)/(size-1),latitudes[Math.floor(index/size)],heights_m[index]+offset]);
}
