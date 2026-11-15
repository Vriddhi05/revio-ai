# DEMO / SYNTHETIC DATA

`reviews.csv` contains 45 fictional customer reviews for Indian consumer businesses. There are 15 reviews each for Jaipur, Rajasthan, India; Chandigarh, India; and Ludhiana, Punjab, India. The names and payment references are fabricated for product demonstrations and are not customer records or financial transaction identifiers.

The examples cover cafes and restaurants, hotels, fitness centres, retail service, takeaway and delivery; they include UPI/PhonePe/Google Pay issues, GST invoices, reservations, parking, peak-hour crowding, and positive, negative, mixed, and neutral feedback. Text is written in Indian English with Hinglish and Hindi examples.

Every row has `is_synthetic=true`. The FastAPI demo seed synchronizes these rows idempotently, updates the previous synthetic fixture in place, and does not overwrite non-demo CSV-imported reviews. The API exposes this same fixture for the import dialog's sample download.
