/* Small shared outline family; static paths only, no remote icon dependency. */
window.odinIcon = (name, filled = false) => {
  const paths = {
    heart:'M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z',
    close:'M6 6l12 12M6 18 18 6',plus:'M12 5v14M5 12h14',minus:'M5 12h14'
  };
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  for(const [key,value] of Object.entries({viewBox:'0 0 24 24',width:'19',height:'19',fill:filled?'currentColor':'none',stroke:'currentColor','stroke-width':'1.7','stroke-linecap':'round','stroke-linejoin':'round','aria-hidden':'true'}))svg.setAttribute(key,value);
  const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',paths[name]||paths.close);svg.append(path);return svg;
};
