/**
 * Extension slot mechanism — Design §4.1/§3.4's escape hatch. See
 * `ExtensionRegistry.ts`'s module doc for the full contract.
 */
export {
  registerPageExtension,
  resolveExtension,
  clearPageExtensions,
  type ExtensionPageProps,
  type ExtensionPageComponent,
  type ExtensionLoader,
} from "./ExtensionRegistry";
export {
  ExtensionFallback,
  type ExtensionFallbackProps,
} from "./ExtensionFallback";
export { ExtensionSlotRenderer } from "./ExtensionSlotRenderer";
export { ExtensionPageRoute } from "./ExtensionPageRoute";
export { buildExtensionMenuCategories } from "./extensionNav";
export {
  registerCellExtension,
  resolveCellExtension,
  clearCellExtensions,
  type ExtensionCellProps,
  type ExtensionCellComponent,
} from "./ExtensionCellRegistry";
export { renderCellSlot } from "./ExtensionCellSlot";
export {
  registerDetailTabExtension,
  resolveDetailTabExtension,
  clearDetailTabExtensions,
  type ExtensionDetailTabProps,
  type ExtensionDetailTabComponent,
  type ExtensionDetailTabLoader,
} from "./ExtensionDetailTabRegistry";
export { ExtensionDetailTabSlot } from "./ExtensionDetailTabSlot";
