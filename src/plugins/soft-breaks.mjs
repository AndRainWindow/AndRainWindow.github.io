// 把段落内的单换行（soft break）渲染成 <br>（硬换行）。
//
// 根因：Obsidian 默认 strictLineBreaks: false，段落内一个换行就换行显示；
// 而标准 Markdown / Sätteri 把单换行折叠成一个空格。本站内容来自 Obsidian，
// 这个插件让网站显示与 Obsidian 一致。
//
// 用 Sätteri 官方 mdast 插件接口（https://docs.astro.build 的 markdown.processor）。
// 只在 text 节点上工作，且仅当其父节点是行内容器时才替换。
//
// 为什么不需要特判代码块 / 行内代码 / 原始 HTML：在 mdast 里 code、inlineCode、
// html、yaml、toml 都把内容放在自己的 value 字段上，没有 text 子节点，
// 因此本插件的访问器根本不会在这些节点内部触发。
//
// heading 刻意排除：标题跨行几乎都是排版事故，换成 <br> 会得到一个看起来
// 断掉的标题。需要跟 Obsidian 完全一致的话，把 'heading' 加进下面的集合即可。

/** 允许出现 <br> 的行内容器节点类型。 */
const INLINE_PARENTS = new Set([
	'paragraph',
	'strong',
	'emphasis',
	'link',
	'delete',
	'superscript',
	'subscript',
	'tableCell',
]);

export const softBreaks = {
	name: 'soft-breaks',

	text(node, ctx) {
		const value = node.value;
		if (typeof value !== 'string' || !value.includes('\n')) {
			return;
		}

		const parent = ctx.parent(node);
		if (!parent || !INLINE_PARENTS.has(parent.type)) {
			return;
		}

		// 兼容 LF（\n）、CRLF（\r\n）与单独的 CR。
		const parts = value.split(/\r\n|\r|\n/);
		const nodes = [];
		for (let i = 0; i < parts.length; i++) {
			// 空片段不产生空的 text 节点，但换行本身仍要留下 <br>。
			if (parts[i] !== '') {
				nodes.push({ type: 'text', value: parts[i] });
			}
			if (i < parts.length - 1) {
				nodes.push({ type: 'break' });
			}
		}

		ctx.replaceNode(node, nodes);
	},
};
