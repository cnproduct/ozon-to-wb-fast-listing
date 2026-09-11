(expectedSku) => {
  // Run only through the active supported browser's read-only evaluate API.
  const sku = String(expectedSku);
  const heading = document.querySelector('[data-widget="webProductHeading"] h1') || document.querySelector('h1');
  const gallery = document.querySelector('[data-widget="webGallery"]');
  const description = document.querySelector('#section-description') || document.querySelector('[data-widget="webDescription"]');
  const characteristics = document.querySelector('#section-characteristics') || document.querySelector('[data-widget="webCharacteristics"]');
  const article = Array.from(document.querySelectorAll('button')).map(e => e.innerText).find(t => /^Артикул:\s*\d+/.test(t.trim()));
  const actualSku = article?.match(/\d+/)?.[0];
  const pathSku = location.pathname.match(/\/product\/(?:[^/]*-)?(\d+)\/?$/)?.[1];
  if (actualSku !== sku || pathSku !== sku) throw new Error('Requested SKU, page article and URL do not agree');
  if (!heading || !gallery || !description || !characteristics) throw new Error('Expand/load description and product gallery first');
  const images = Array.from(gallery.querySelectorAll('img')).map(e => ({url:e.currentSrc || e.src,alt:e.alt}));
  const productImages = images.filter(e => /\/s3\/multimedia[^/]*\//.test(e.url));
  if (!productImages.length) throw new Error('No observed product gallery images');
  return {
    sku, url:location.origin + location.pathname, captured_at:new Date().toISOString(),
    title:heading.innerText.trim(), description:description.innerText.trim(),
    characteristics:characteristics.innerText.trim(),
    price_text:document.querySelector('[data-widget="webPrice"]')?.innerText || '',
    gallery_scope:'webGallery', gallery:productImages, gallery_text:gallery.innerText,
    unresolved_image_count:images.filter(e=>!e.url || /^data:/.test(e.url)).length
  };
}
