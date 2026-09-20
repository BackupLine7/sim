const C = window.Cesium;

export function hasTerrain(data) {
  return Boolean(data.terrain);
}

export function terrainHeightRangeM(data, fallbackGroundM) {
  const heights = data.terrain?.heights_m ?? [fallbackGroundM];
  return [Math.min(...heights), Math.max(...heights)];
}

export function terrainMeshPrimitive(data, image) {
  performance.mark('terrain-mesh-start');
  const {size, latitudes, heights_m: heights} = data.terrain;
  const border=[];
  for(let col=0;col<size;col++)border.push(col);
  for(let row=1;row<size;row++)border.push(row*size+size-1);
  for(let col=size-2;col>=0;col--)border.push((size-1)*size+col);
  for(let row=size-2;row>0;row--)border.push(row*size);
  const positions = new Float64Array((size*size+border.length)*3);
  const st = new Float32Array((size*size+border.length)*2);
  const indices = new Uint32Array(((size-1)*(size-1)+border.length)*6);
  const point = new C.Cartesian3();
  for (let row=0;row<size;row++) for (let col=0;col<size;col++) {
    const i=row*size+col;
    C.Cartesian3.fromDegrees(data.bounds[0]+(data.bounds[2]-data.bounds[0])*col/(size-1),latitudes[row],heights[i],C.Ellipsoid.WGS84,point);
    positions.set([point.x,point.y,point.z],i*3);
    st[i*2]=col/(size-1);st[i*2+1]=1-row/(size-1);
  }
  let cursor=0;
  for (let row=0;row<size-1;row++) for (let col=0;col<size-1;col++) {
    const a=row*size+col,b=a+1,c=a+size,d=c+1;
    indices.set([a,c,b,b,c,d],cursor);cursor+=6;
  }
  const skirtDepth=Math.max(...heights)-Math.min(...heights)+1;
  border.forEach((upper,index)=>{
    const row=Math.floor(upper/size),col=upper%size,lower=size*size+index;
    C.Cartesian3.fromDegrees(data.bounds[0]+(data.bounds[2]-data.bounds[0])*col/(size-1),latitudes[row],heights[upper]-skirtDepth,C.Ellipsoid.WGS84,point);
    positions.set([point.x,point.y,point.z],lower*3);
    st.set(st.subarray(upper*2,upper*2+2),lower*2);
    const next=(index+1)%border.length;
    indices.set([upper,lower,border[next],border[next],lower,size*size+next],cursor);cursor+=6;
  });
  const geometry=C.GeometryPipeline.computeNormal(new C.Geometry({
    attributes:{
      position:new C.GeometryAttribute({componentDatatype:C.ComponentDatatype.DOUBLE,componentsPerAttribute:3,values:positions}),
      st:new C.GeometryAttribute({componentDatatype:C.ComponentDatatype.FLOAT,componentsPerAttribute:2,values:st}),
    },
    indices,primitiveType:C.PrimitiveType.TRIANGLES,boundingSphere:C.BoundingSphere.fromVertices(positions),
  }));
  const primitive = new C.Primitive({
    geometryInstances:new C.GeometryInstance({geometry}),
    appearance:new C.MaterialAppearance({material:C.Material.fromType('Image',{image}),translucent:false,closed:false,faceForward:true}),
    asynchronous:false,
  });
  performance.measure('terrain-mesh','terrain-mesh-start');
  performance.clearMarks('terrain-mesh-start');
  performance.clearMeasures('terrain-mesh');
  return primitive;
}

export function flatImageryRectangle(data, image, groundM) {
  return {
    rectangle: {
      coordinates: C.Rectangle.fromDegrees(...data.bounds),
      height: groundM,
      material: new C.ImageMaterialProperty({ image }),
      outline: false,
    },
  };
}
