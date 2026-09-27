-- Instagram (27/09, Patrick): roupa e pose de cada post, pra ela não repetir roupa nem pose no feed.
ALTER TABLE ig_posts ADD COLUMN roupa TEXT;
ALTER TABLE ig_posts ADD COLUMN pose TEXT;
