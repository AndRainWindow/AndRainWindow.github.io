// @ts-check

import mdx from '@astrojs/mdx';
import sitemap from '@astrojs/sitemap';
import { satteri } from '@astrojs/markdown-satteri';
import { defineConfig, fontProviders } from 'astro/config';
import { softBreaks } from './src/plugins/soft-breaks.mjs';

// https://astro.build/config
export default defineConfig({
	site: 'https://AndRainWindow.github.io',
	integrations: [mdx(), sitemap()],
	markdown: {
		// satteri() 就是 Astro 7 的默认处理器，这里只是给它挂一个 mdast 插件。
		// 没有 remark/rehype：那几个在 satteri 下已被弃用且会被静默忽略。
		processor: satteri({ mdastPlugins: [softBreaks] }),
	},
	fonts: [
		{
			provider: fontProviders.local(),
			name: 'Atkinson',
			cssVariable: '--font-atkinson',
			fallbacks: ['sans-serif'],
			options: {
				variants: [
					{
						src: ['./src/assets/fonts/atkinson-regular.woff'],
						weight: 400,
						style: 'normal',
						display: 'swap',
					},
					{
						src: ['./src/assets/fonts/atkinson-bold.woff'],
						weight: 700,
						style: 'normal',
						display: 'swap',
					},
				],
			},
		},
	],
});
