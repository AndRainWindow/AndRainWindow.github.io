import { getCollection } from 'astro:content';
import rss from '@astrojs/rss';
import { SITE_DESCRIPTION, SITE_TITLE } from '../consts';

export async function GET(context) {
	// hidden / deleted 的文章由发布工具的博客管理标记，不进入 RSS。
	const posts = (await getCollection('blog')).filter(
		(post) => !post.data.hidden && !post.data.deleted
	);
	return rss({
		title: SITE_TITLE,
		description: SITE_DESCRIPTION,
		site: context.site,
		items: posts.map((post) => ({
			...post.data,
			link: `/blog/${post.id}/`,
		})),
	});
}
