window.PixelTriangleRenderer=function(renderer){
 renderer.drawTriangle=function(img,x0,y0,u0,v0,x1,y1,u1,v1,x2,y2,u2,v2){
  const c=this.ctx;u0*=img.width;u1*=img.width;u2*=img.width;v0*=img.height;v1*=img.height;v2*=img.height;
  const X1=x1-x0,Y1=y1-y0,X2=x2-x0,Y2=y2-y0,U1=u1-u0,V1=v1-v0,U2=u2-u0,V2=v2-v0,det=U1*V2-U2*V1;if(Math.abs(det)<1e-9)return;
  const a=(V2*X1-V1*X2)/det,b=(V2*Y1-V1*Y2)/det,d=(U1*X2-U2*X1)/det,e=(U1*Y2-U2*Y1)/det,cx=(x0+x1+x2)/3,cy=(y0+y1+y2)/3;
  const pad=(x,y)=>{const len=Math.hypot(x-cx,y-cy)||1;return[x+(x-cx)/len*.12,y+(y-cy)/len*.12]};
  c.save();c.beginPath();c.moveTo(...pad(x0,y0));c.lineTo(...pad(x1,y1));c.lineTo(...pad(x2,y2));c.closePath();c.clip();c.transform(a,b,d,e,x0-a*u0-d*v0,y0-b*u0-e*v0);c.drawImage(img,0,0);c.restore();
 };
};
