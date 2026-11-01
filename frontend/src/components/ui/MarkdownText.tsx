import Markdown from "react-markdown";

/**
 * Draws an answer written by a model, which usually comes in Markdown.
 *
 * Exists so an answer reads as text and not as literal asterisks. Raw HTML inside the answer stays
 * as plain text, because what a model writes cannot be trusted as markup.
 *
 * @param props.text - The answer.
 * @returns The formatted text.
 */
export function MarkdownText({ text }: { text: string }) {
  return (
    <div className="markdown-text text-sm">
      <Markdown>{text}</Markdown>
    </div>
  );
}
