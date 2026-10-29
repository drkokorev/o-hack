/* Navigation and a short optional introduction; the map keeps its own camera. */
window.createJourneyUI = ({fill, onTransfer}) => {
  const $ = id => document.getElementById(id);
  let active = "chat", hasResults = false, resultCount = 0, tourStep = 0, currentKind="";
  const steps = [
    {title:"С кем, куда и когда?", text:"Опишите, с кем, где и когда вы хотели бы побыть. Можно начать с желания — остальное уточним вместе.", example:"На выходные в Казань вдвоём. Хочется гулять по центру и жить рядом."},
    {title:"Выбирайте на глобусе", text:"Вращайте и приближайте глобус. Нажмите на видимую метку. Число на точке означает группу: приблизьте её, чтобы увидеть места внутри. Когда поездка выбрана, здесь появится её маршрут."},
    {title:"Соберите поездку под себя", text:"Сравните варианты, раскройте отель, дорогу и трансферы. Город отправления подскажем по IP, если получится. Нажмите на значение в сводке поездки, чтобы изменить его. Сводка находится над перепиской: откройте «Условия поездки». Поездка сохраняется в этой вкладке."}
  ];
  if(window.ODIN_EMBED)steps.splice(1,1);
  const scrollTo = target => requestAnimationFrame(() => {
    if(target==="head"){window.scrollTo({top:0,behavior:"instant"});return;}
    const node = $(target); if (!node) return;
    node.scrollIntoView({block:"start", behavior:matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth"});
    if (target === "view") node.focus({preventScroll:true});
  });
  function show(tab, scroll = true) {
    if (tab === "results" && !hasResults) return;
    if(window.ODIN_EMBED && tab === "map")return;
    active = tab;
    document.body.dataset.panel = tab;
    document.body.classList.toggle("show-map", tab !== "chat");
    document.querySelectorAll("[data-panel]").forEach(button => {
      if (button.tagName === "BUTTON") button.setAttribute("aria-pressed", String(button.dataset.panel === tab));
    });
    $("mobile-map").textContent = tab === "chat" ? "Глобус" : "В чат";
    $("mobile-map").setAttribute("aria-expanded", String(tab !== "chat"));
    window.dispatchEvent(new Event("resize"));
    if (scroll && tab !== "chat") scrollTo(tab === "results" ? "view" : "head");
  }
  function update(data) {
    const p = data?.payload || {};currentKind=p.kind||"";
    hasResults = ["ideas","destinations","packages","hotels","cart","payment","order","real_hotels","real_hotel_selected","place_info","tent_transport","tent_cart","tent_order"].includes(p.kind);
    resultCount = p.items?.length || 0;
    const cart = ["cart","payment","order","tent_cart","tent_order"].includes(p.kind);
    const label = cart ? "Ваша поездка" : resultCount ? `Варианты · ${resultCount}` : "Варианты";
    $("panel-results").textContent = label;
    $("panel-results").disabled = !hasResults;
    $("results-jump").hidden = true;
    $("results-jump").textContent = cart ? "Посмотреть поездку ↓" : resultCount ? `Посмотреть варианты: ${resultCount} ↓` : "Посмотреть результат ↓";
    $("map-label").textContent = p.trip ? "Маршрут вашей поездки" : "Выберите место на глобусе";
    $("map-label").hidden = !data;
    if (!hasResults && active === "results") show("chat", false);
  }
  function addResultLink(message) {
    if (!hasResults || !message) return;
    const button = document.createElement("button");
    button.type="button"; button.className="btn accent reply-results";
    const linkKind=currentKind;
    button.textContent = currentKind==="cart"?"Перейти к оплате":currentKind==="payment"?"Выбрать способ оплаты":resultCount ? `Посмотреть ${resultCount} ${resultCount === 1 ? "вариант" : resultCount < 5 ? "варианта" : "вариантов"}` : "Посмотреть поездку";
    button.onclick=()=>{if(linkKind==="cart"&&currentKind==="cart")send("да, оформляй");show("results");}; message.append(button);
  }
  function markTourSeen() { try { localStorage.setItem("odin.tour.v2", "seen"); } catch (_) {} }
  function paintTour() {
    const step=steps[tourStep];
    $("tour-counter").textContent=`${tourStep+1} из ${steps.length}`;
    $("tour-title").textContent=step.title; $("tour-text").textContent=step.text;
    $("tour-example").hidden=!step.example; $("tour-example").textContent=step.example || "";
    $("tour-back").hidden=tourStep===0;
    $("tour-next").textContent=tourStep===steps.length-1 ? "Начать поездку" : "Дальше";
  }
  function openTour() { tourStep=0;paintTour();if(!$("tour-dialog").open)$("tour-dialog").showModal(); }
  $("tour-next").onclick=()=> {if(tourStep<steps.length-1){tourStep++;paintTour();}else{$("tour-dialog").close();markTourSeen();$("text").focus();}};
  $("tour-back").onclick=()=>{tourStep=Math.max(0,tourStep-1);paintTour();};
  $("tour-skip").onclick=()=>{$("tour-dialog").close();markTourSeen();};
  $("tour-dialog").addEventListener("close",markTourSeen);
  $("tour-example").onclick=()=>{$("tour-dialog").close();markTourSeen();show("chat",false);fill(steps[0].example);};
  $("tour-open").onclick=()=>{document.getElementById("about-dialog").close();openTour();};
  document.querySelectorAll("button[data-panel]").forEach(button=>button.onclick=()=>show(button.dataset.panel));
  $("results-jump").onclick=()=>show("results");
  $("mobile-map").onclick=()=>show(active==="chat" ? "map" : "chat");
  return {show,update,addResultLink,openTour,
    firstVisit:()=>{let seen=false;try{seen=Boolean(localStorage.getItem("odin.tour.v2"));}catch(_){}if(!seen)openTour();},
    panel:()=>active,
    transfer:kind=>onTransfer(kind)};
};
