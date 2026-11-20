// PostCSS plugin: keep frappe-ui's global CSS inside `.slcm-fui`.
//
// Tailwind's preflight, @tailwindcss/forms and frappe-ui's theme plugin write
// rules for bare elements (`*`, `html`, `button`, `[type='text']`, …) and put
// their design tokens on `:root`. Inside desk those would restyle the whole
// page and clash with desk's own variables. This rewrites them:
//
//   :root, html, body          -> .slcm-fui
//   [data-theme="dark"]        -> [data-theme="dark"] .slcm-fui
//   *, button, [type='text']   -> :where(.slcm-fui) *, …   (zero added specificity)
//
// Class selectors (frappe-ui components, utilities already prefixed by
// tailwind's `important: ".slcm-fui"`) are left alone.

const SCOPE = ".slcm-fui";
const WHERE = `:where(${SCOPE})`;
const DARK = /^\[data-theme=(["'])dark\1\]/;

function scopeSelector(selector) {
	const s = selector.trim();

	if (s.includes(SCOPE)) return s;
	// The dashboard's export (print) rules have to reach desk's own page boxes, and only apply
	// while App.vue has put `slcm-printing` on <html>, so they are left page-wide on purpose.
	if (/^html\.slcm-printing\b/.test(s)) return s;
	if (s === ":root" || s === "html" || s === "body" || s === ":host") return SCOPE;

	const dark = s.match(DARK);
	if (dark) {
		const rest = s.slice(dark[0].length).trim();
		return rest ? `${dark[0]} ${WHERE} ${rest}` : `${dark[0]} ${SCOPE}`;
	}

	// Components and utilities: plain class selectors stay global names.
	if (s.startsWith(".")) return s;

	// `html …` / `body …` descendants.
	const htmlBody = s.match(/^(html|body)\b\s*(.*)$/);
	if (htmlBody) return htmlBody[2] ? `${WHERE} ${htmlBody[2]}` : SCOPE;

	// `*` also has to match the scope root itself (box-sizing, tw vars).
	if (s === "*") return `${WHERE}, ${WHERE} *`;

	return `${WHERE} ${s}`;
}

const plugin = () => ({
	postcssPlugin: "slcm-fui-scope",
	Rule(rule) {
		if (rule.__slcmScoped) return;
		const parent = rule.parent;
		if (parent && parent.type === "atrule" && /keyframes|font-face/i.test(parent.name)) return;

		rule.selectors = rule.selectors.flatMap((sel) => scopeSelector(sel).split(/,\s*(?![^()]*\))/));
		rule.__slcmScoped = true;
	},
});
plugin.postcss = true;

export default plugin;
