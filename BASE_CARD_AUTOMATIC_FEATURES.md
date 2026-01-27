# RamsesBaseCard Automatic Features

All cards extending `RamsesBaseCard` automatically receive the following features without any card-specific code:

## 1. Version Mismatch Banner

**Automatic injection of version mismatch warning banner**

- Displayed when frontend and backend versions don't match
- Only injects/removes when mismatch state changes (not on every render)
- Prevents DOM thrashing and unnecessary re-renders
- Shows frontend and backend versions with hard refresh instructions

**Implementation:**

- `_injectVersionBanner()` called automatically in base card `render()` method
- Tracks state with `_lastVersionMismatchState` to avoid redundant DOM manipulation
- Banner selector: `[style*="background: #ff9800"]`

**No card-specific code needed** - just extend `RamsesBaseCard`

## 2. UI State Preservation

**Automatic preservation of user input state during re-renders**

When a card re-renders (which wipes `shadowRoot.innerHTML`), the base card automatically:

- **Preserves focus** on active input elements
- **Preserves text selection** and cursor position in inputs
- **Preserves scroll positions** for all scrollable elements
- **Restores everything** after the DOM is recreated

**Implementation:**

- `_preserveUIState()` called before `_renderContent()`
- `_restoreUIState()` called after `_renderContent()`
- Both called automatically in base card `render()` method

**Benefits:**

- ✅ No focus loss when typing in search fields
- ✅ Scroll positions maintained during updates
- ✅ Input values preserved during re-renders
- ✅ Better user experience with frequent updates

**No card-specific code needed** - just extend `RamsesBaseCard`

## 3. Cards Covered

All cards extending `RamsesBaseCard` get these features automatically:

- **HVAC Fan Card** (`hvac-fan-card.js`)
- **Log Explorer** (`ramses-log-explorer.js`)
- **Packet Log Explorer** (`ramses-packet-log-explorer.js`)
- **Traffic Analyser** (`ramses-traffic-analyser.js`)
- **Future cards** - any new card extending `RamsesBaseCard`

## 4. Implementation Details

### Base Card render() Flow

```javascript
render() {
  // ... validation checks ...

  // 1. Preserve UI state BEFORE rendering
  const uiState = this._preserveUIState();

  // 2. Call subclass rendering (wipes DOM)
  this._renderContent();

  // 3. Restore UI state AFTER rendering
  this._restoreUIState(uiState);

  // 4. Inject version banner if needed
  this._injectVersionBanner();
}
```

### Card-Specific Code

Cards only need to implement `_renderContent()`:

```javascript
_renderContent() {
  this.shadowRoot.innerHTML = `
    <style>...</style>
    <ha-card>
      <!-- Card content -->
    </ha-card>
  `;

  // Bind event listeners
  this._bindEventListeners();
}
```

**No need to:**

- Call `_preserveUIState()` or `_restoreUIState()` manually
- Inject version banner manually
- Track UI state or scroll positions

## 5. Advanced Usage

If a card needs to preserve specific scroll elements, it can override the default behavior:

```javascript
_renderContent() {
  // Override with specific scroll element IDs
  const uiState = this._preserveUIState(['myScrollDiv', 'anotherScrollArea']);

  this._renderContentImpl();

  this._restoreUIState(uiState);
}
```

But this is **optional** - the base implementation works for most cases.

## 6. Testing

To verify automatic features work:

1. **Version Banner:**
   - Set different frontend/backend versions
   - Banner should appear on ALL cards
   - Banner should only update when mismatch state changes

2. **UI State Preservation:**
   - Type in a search field
   - Trigger a re-render (e.g., WebSocket update)
   - Focus should remain, text should be preserved
   - Scroll position should be maintained

## 7. Migration Notes

**Before (manual implementation):**

```javascript
_renderContent() {
  const uiState = this._preserveUIState(['output']);
  this._renderContentImpl();
  this._restoreUIState(uiState);
}
```

**After (automatic):**

```javascript
_renderContent() {
  this._renderContentImpl();
}
```

The base card now handles UI state preservation automatically for all cards.
