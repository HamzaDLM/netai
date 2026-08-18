import { isUnifiedDiffText, normalizeUnifiedPatch } from './config-diff.adapter'

const fencedCodeBlock = /(```|~~~)[^\n]*\n([\s\S]*?)\1/g

/** Replace a raw patch already represented by a config-diff artifact. */
export function replaceRenderedUnifiedDiffFences(markdown: string, renderedPatches: string[]): string {
	const fingerprints = new Set(renderedPatches.filter(isUnifiedDiffText).map(patch => normalizeUnifiedPatch(patch).trim()))
	if (fingerprints.size === 0) return markdown

	return markdown.replace(fencedCodeBlock, (block: string, _fence: string, body: string) => {
		if (!fingerprints.has(normalizeUnifiedPatch(body).trim())) return block
		return '\n\n_The full patch is shown in the diff viewer._\n\n'
	})
}
