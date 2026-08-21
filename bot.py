async def forward_post(messages):
    print(f"🚨 ELABORAZIONE POST ({len(messages)} elementi)...")
    
    text_msg = next((m for m in messages if m.text), messages[0])
    text = text_msg.text or ""

    # Estrazione Titolo e Prezzo
    article_match = re.search(r'Article:\s*(.*)', text)
    price_match = re.search(r'Price:\s*(.*)', text)

    title = article_match.group(1).strip() if article_match else "Prodotto Esclusivo"
    price = price_match.group(1).strip() if price_match else "N/A"

    # Selezione dinamica emoji
    emoji = get_product_emoji(title)

    # Estrazione Link USFans
    usfans_link = None
    if text_msg.entities:
        for entity in text_msg.entities:
            if hasattr(entity, 'url') and entity.url and 'usfans' in entity.url.lower():
                usfans_link = entity.url
                break

    if not usfans_link:
        url_search = re.search(r'https?://[^\s]*usfans[^\s]*', text)
        if url_search:
            usfans_link = url_search.group(0)

    if not usfans_link:
        usfans_link = "https://usfans.com"

    # Applicazione Tag Affiliato
    if 'affcode=' in usfans_link:
        usfans_link = re.sub(r'(affcode=)[^&\s]+', f'affcode={AFFILIATE_TAG}', usfans_link)
    elif '?' in usfans_link:
        usfans_link += f'&affcode={AFFILIATE_TAG}'
    else:
        usfans_link += f'?affcode={AFFILIATE_TAG}'

    new_text = (
        f"{emoji} **{title}**\n"
        f"💰 **Prezzo: {price}€**\n\n"
        f"🎁 **BONUS BENVENUTO:** Usa i tuoi coupon per risparmiare fino al 40% sul tuo ordine!\n"
        f"🔥 **Batch:** Qualità e dettagli top"
    )

    buttons = [
        [Button.url("🛒 ACQUISTA PRODOTTO", usfans_link)],
        [Button.url("🎁 ISCRIVITI + 40% DI SCONTO", LINK_SCONTO)]
    ]

    try:
        # Scarica i media in memoria (bytes) tramite user_client per poi farli inviare al bot
        downloaded_files = []
        for m in messages:
            if m.media:
                file_bytes = await user_client.download_media(m.media, file=bytes)
                if file_bytes:
                    downloaded_files.append(file_bytes)

        if downloaded_files:
            await bot_client.send_file(
                TARGET_CHAT, 
                downloaded_files, 
                caption=new_text, 
                buttons=buttons
            )
        else:
            await bot_client.send_message(TARGET_CHAT, new_text, buttons=buttons)
            
        print("✅ ALBUM, EMOJI E BOTTONI PUBBLICATI CON SUCCESSO!")
    except Exception as e:
        print(f"❌ Errore durante l'invio: {e}")
