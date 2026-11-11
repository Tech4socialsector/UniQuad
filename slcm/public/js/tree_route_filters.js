// Frappe builds a tree view (Account, Cost Center, ...) once and reuses it, and reads route options such as
// { company } only while building it. So Company > View > Cost Centers opened the tree of whichever company it was
// first shown with (the default company). Apply the route's filters again when a cached tree is shown.
(() => {
	const Factory = frappe.views && frappe.views.TreeFactory;
	const TreeView = frappe.views && frappe.views.TreeView;
	if (!Factory || !TreeView) return;

	function tree_filters(tree, built = true) {
		const options = frappe.route_options || {};
		return (tree.opts.filters || []).filter(
			(f) => options[f.fieldname] && (!built || (tree.page && tree.page.fields_dict[f.fieldname]))
		);
	}

	const make_filters = TreeView.prototype.make_filters;
	TreeView.prototype.make_filters = function () {
		const used = tree_filters(this, false).length;
		make_filters.call(this);
		// consumed: a later visit from the sidebar must not bring them back
		if (used) frappe.route_options = null;
	};

	const on_show = Factory.prototype.on_show;
	Factory.prototype.on_show = function () {
		const tree = frappe.views.trees[frappe.get_route()[1]];
		const filters = tree ? tree_filters(tree) : [];
		const options = frappe.route_options || {};
		const changed = filters.filter((f) => tree.page.fields_dict[f.fieldname].get_value() !== options[f.fieldname]);
		if (filters.length) frappe.route_options = null;
		if (changed.length) {
			// each filter's change handler rebuilds the tree
			changed.forEach((f) => tree.page.fields_dict[f.fieldname].set_value(options[f.fieldname]));
			return;
		}
		return on_show.call(this);
	};
})();
