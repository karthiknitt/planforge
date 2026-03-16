/**
 * JsonLd — injects structured data (JSON-LD) for SEO rich snippets.
 * Content is always the output of JSON.stringify on our own static data objects.
 * No user input is ever passed here, so XSS risk is zero.
 */
export function JsonLd({ data }: { data: object }) {
  const json = JSON.stringify(data);
  // biome-ignore lint/security/noDangerouslySetInnerHtml: JSON.stringify on own static data is safe
  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: json }} />;
}
