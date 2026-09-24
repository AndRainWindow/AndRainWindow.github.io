import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const blog = defineCollection({
	loader: glob({
		pattern: '**/*.{md,mdx}',
		base: './src/content/blog',
	}),

	schema: z.object({
		title: z.string(),

		topics: z.string().optional(),

		date: z.coerce.date().optional(),
		updated: z.coerce.date().optional(),

		heroImage: z.string().optional(),

		wordCount: z.number().optional(),
		readingTime: z.number().optional(),

		// 博客管理设置的可见性标志（发布工具写入）。
		hidden: z.boolean().optional(),
		deleted: z.boolean().optional(),
	}),
});

export const collections = {
	blog,
};