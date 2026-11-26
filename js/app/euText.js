// EU wording for the interface. The engine came from a US map, so its copy talks about states, counties and metros. The US becomes Europe (the map covers more than the EU).
// Instead of rewriting every template, visible text nodes and a few attributes are passed through these rules as they
// appear (a MutationObserver). Data names (cities, regions) are not affected by the rules in practice.

const RULES = [
  [/\bthe contiguous United States\b/g, "Europe"],
  [/\bUNITED STATES\b/g, "EUROPE"],
  [/\bUnited States\b/g, "Europe"],
  [/\bthe lower[- ]48\b/gi, "the map"],
  [/\blower[- ]48\b/gi, "European"],
  [/\bAmericans\b/g, "Europeans"],
  [/\bAmerica\b/g, "Europe"],
  [/\bthe U\.S\.(?= [a-z])/g, "the European"],
  [/\bthe U\.S\./g, "Europe"],
  [/\bU\.S\. ?/g, "Europe "],
  [/\bthe US\b/g, "Europe"],
  [/\bUS\b/g, "Europe"],
  [/\bnationally\b/g, "Europe-wide"],
  [/\bnational capital\b/g, "capital"],
  [/\bNLCD( 2021)?\b/g, "WorldCover 2021"],
  [/\bInterstates?\b/g, "Motorways"],
  [/\bdollars\b/g, "euros"],
  [/\bboardings\b/g, "passengers"],
  [/\bmetros & micros\b/gi, "metro regions"],
  [/\bMicropolitan area\b/g, "City region"],
  [/\bmicropolitan area\b/g, "city region"],
  [/\bMICROPOLITAN AREA\b/g, "CITY REGION"],
  [/\bmetro or micro area\b/g, "metro region"],
  [/\bmicro areas?\b/g, "metro regions"],
  [/\bstate's\b/g, "country's"],
  [/\bstates'\b/g, "countries'"],
  [/\bStates\b/g, "Countries"],
  [/\bSTATES\b/g, "COUNTRIES"],
  [/\bstates\b/g, "countries"],
  [/\bState\b/g, "Country"],
  [/\bSTATE\b/g, "COUNTRY"],
  [/\bstate\b/g, "country"],
  [/\bcounty's\b/g, "region's"],
  [/\bCounties\b/g, "Regions"],
  [/\bCOUNTIES\b/g, "REGIONS"],
  [/\bcounties\b/g, "regions"],
  [/\bCounty\b/g, "Region"],
  [/\bCOUNTY\b/g, "REGION"],
  [/\bcounty\b/g, "region"],
  [/\bcountrys\b/g, "countries"],
  [/\bshort tons\b/g, "tonnes"],
  [/ \(BLS withheld a region.s figure\)/g, ""],
  [/, all ownerships \(federal and country only for the Civic Center and Defense District\)/g, ""],
  [/\bone vintage of the Census population estimates\b/g, "Eurostat's 1 January population figures"],
  [/\bCensus population estimates\b/g, "Eurostat population figures"],
  [/\bCensus estimates\b/g, "Eurostat, 1 January"],
];

export function euText(s) {
  if (!s || typeof s !== "string" || !/[A-Za-z]/.test(s)) return s;
  let out = s;
  for (const [re, to] of RULES) out = out.replace(re, to);
  return out;
}

const ATTRS = ["title", "placeholder", "aria-label", "alt", "data-tip"];
const SKIP = new Set(["SCRIPT", "STYLE", "TEXTAREA", "INPUT", "CODE"]);

function fixNode(node) {
  if (node.nodeType === 3) {
    const p = node.parentNode;
    if (p && SKIP.has(p.nodeName)) return;
    const v = node.nodeValue, n = euText(v);
    if (n !== v) node.nodeValue = n;
    return;
  }
  if (node.nodeType !== 1 || SKIP.has(node.nodeName) && node.nodeName !== "INPUT") {
    if (node.nodeType === 1 && node.nodeName === "INPUT") fixAttrs(node);
    return;
  }
  fixAttrs(node);
  const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
  let n;
  while ((n = walker.nextNode())) {
    if (n.nodeType === 1) fixAttrs(n);
    else if (!SKIP.has(n.parentNode?.nodeName)) {
      const v = n.nodeValue, t = euText(v);
      if (t !== v) n.nodeValue = t;
    }
  }
}

function fixAttrs(el) {
  for (const a of ATTRS) {
    const v = el.getAttribute?.(a);
    if (v) {
      const n = euText(v);
      if (n !== v) el.setAttribute(a, n);
    }
  }
}

export function installEuText(root = document.body) {
  fixNode(root);
  document.title = euText(document.title);
  const mo = new MutationObserver((muts) => {
    for (const m of muts) {
      if (m.type === "characterData") fixNode(m.target);
      else if (m.type === "attributes") fixAttrs(m.target);
      else m.addedNodes.forEach(fixNode);
    }
  });
  mo.observe(root, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ATTRS });
}
