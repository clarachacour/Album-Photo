import React from "react";
import { CoverSpine } from "@/components/CoverSpine";
import { spineRatio } from "@/lib/printDims";
import { AlbumPage } from "@/components/book/AlbumPage";
import { CoverFrontPage } from "@/components/book/CoverFrontPage";
import { CoverBackPage } from "@/components/book/CoverBackPage";
import Flipbook from "@/components/Flipbook";

export function BookRenderer({
  album,
  template,
  orientation,
  bookRef,
  onSelectItem,
  onUpdateItem,
  onDeleteItem,
  swapSourceItemId,
  onSwapAction,
  onAddPhotoAt,
  onReplacePhoto,
  onReorderLayer,
  onApplyLayout,
  onDeletePage,
  placingPhotoId,
  onPhotoPlaced,
  selectedId,
  cropMode,
  onEnterCrop,
  onExitCrop,
  placingText,
  onPlaceText,
  onStartAddText,
  autoEditItemId,
  onTextEditHandled,
  onFlip,
  coverImageUrl,
  coverSel,
  onSelectCover,
  onSelectCoverTitle,
  onSelectCoverItem,
  onUpdateCoverTitle,
  onUpdateCoverItem,
  onUpdateCover,
  onSelectSpine,
}) {
  const blank = (
    <div className={`w-full ${orientation === "landscape" ? "aspect-[1.414/1]" : "aspect-[1/1.414]"} bg-[color:var(--paper)]`} />
  );
  // Real page count is known here (unlike the creation wizard's cover step,
  // which runs before any photos exist), so the spine matches exactly what
  // the PDF export will produce.
  const spineWidthPercent = spineRatio(album.size, orientation, (album.pages || []).length) * 100;
  const pages = [
    <div key="cover-front" className="relative h-full w-full">
      {/* The front cover keeps its full, correctly-proportioned size
          (matching the chosen format/orientation exactly) — the spine is
          attached as an extra strip just outside its left edge instead of
          eating into its width, which used to squash it and leave a gap. */}
      <div
        className="absolute top-0 h-full"
        style={{ width: `${spineWidthPercent}%`, right: "calc(100% + 3px)" }}
      >
        <CoverSpine
          title={album.title}
          template={template}
          cover={album.cover || {}}
          editable={!album.was_ordered}
          selectedZone={coverSel?.mode}
          onSelectTitle={() => onSelectSpine && onSelectSpine("spine-title")}
          onSelectSubtitle={() => onSelectSpine && onSelectSpine("spine-subtitle")}
          onSelectCaption={() => onSelectSpine && onSelectSpine("spine-caption")}
          onSelectLogo={() => onSelectSpine && onSelectSpine("spine-logo")}
          onSelectDivider={() => onSelectSpine && onSelectSpine("spine-divider")}
          onUpdateCover={onUpdateCover}
        />
      </div>
      {/* A thin visible seam between the spine and the cover, matching the
          gap already used in the "Make it yours" flat-spread layout — makes
          it clear these are two separate, distinct pieces. */}
      <div
        className="absolute top-0 h-full bg-[color:var(--ink)]/70"
        style={{ width: "3px", right: "100%" }}
      />
      <div className="h-full w-full">
        <CoverFrontPage
          template={template}
          title={album.title}
          orientation={orientation}
          coverImageUrl={coverImageUrl}
          cover={album.cover || {}}
          editable={!album.was_ordered}
          onSelectCover={() => onSelectCover("front")}
          onSelectTitle={onSelectCoverTitle}
          onSelectItem={(item) => onSelectCoverItem(item, "front")}
          onUpdateTitle={onUpdateCoverTitle}
          onUpdateItem={(itemId, patch) => onUpdateCoverItem(itemId, patch, "front")}
          titleSelected={coverSel?.mode === "title"}
          selectedItemId={coverSel?.mode === "item" && coverSel?.side === "front" ? coverSel.itemId : null}
        />
      </div>
    </div>,
    <React.Fragment key="blank-inner-front">{blank}</React.Fragment>,
    ...(album.pages || []).map((page, i) => (
      <AlbumPage
        key={page.id || i}
        page={page}
        orientation={orientation}
        pageIndex={i}
        editable={!album.was_ordered}
        selectedItemId={selectedId}
        onSelectItem={(item) => onSelectItem(i, item)}
        onUpdateItem={(itemId, patch) => onUpdateItem(i, itemId, patch)}
        onDeleteItem={(itemId) => onDeleteItem(i, itemId)}
        swapSourceItemId={swapSourceItemId}
        onSwapAction={onSwapAction}
        onAddPhotoAt={(photoId, box) => onAddPhotoAt(i, photoId, box)}
        onReplacePhoto={(itemId, photoId) => onReplacePhoto(i, itemId, photoId)}
        onReorderLayer={(itemId, direction) => onReorderLayer(i, itemId, direction)}
        placingPhotoId={placingPhotoId}
        onPhotoPlaced={onPhotoPlaced}
        onApplyLayout={(patternName) => onApplyLayout(i, patternName)}
        onDeletePage={() => onDeletePage(i)}
        cropMode={cropMode}
        onEnterCrop={onEnterCrop}
        onExitCrop={onExitCrop}
        placingText={placingText}
        onPlaceText={(box) => onPlaceText(i, box)}
        onStartAddText={onStartAddText}
        autoEditItemId={autoEditItemId}
        onTextEditHandled={onTextEditHandled}
      />
    )),
    <React.Fragment key="blank-inner-back">{blank}</React.Fragment>,
    <CoverBackPage
      key="cover-back"
      template={template}
      country={album.country}
      orientation={orientation}
      cover={album.cover || {}}
      editable={!album.was_ordered}
      onSelectCover={() => onSelectCover("back")}
      onSelectItem={(item) => onSelectCoverItem(item, "back")}
      onUpdateItem={(itemId, patch) => onUpdateCoverItem(itemId, patch, "back")}
      selectedItemId={coverSel?.mode === "item" && coverSel?.side === "back" ? coverSel.itemId : null}
    />,
  ];
  return <Flipbook ref={bookRef} pages={pages} orientation={orientation} onFlip={onFlip} />;
}
