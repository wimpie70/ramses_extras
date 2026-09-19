/**
 * Device Status Card styles.
 *
 * @module device-status-card-styles
 */

export const deviceStatusCardStyle = `
  .r-xtrs-devstat-content {
    padding: 8px 16px 16px;
  }

  .r-xtrs-devstat-pool {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 12px;
    padding: 8px;
    border-radius: 8px;
    background: var(--secondary-background-color, rgba(0, 0, 0, 0.04));
  }

  .r-xtrs-devstat-pool-item {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    padding: 4px 8px;
    border-radius: 6px;
    background: var(--card-background-color, #fff);
    border: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
  }

  .r-xtrs-devstat-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .r-xtrs-devstat-dot.on {
    background: var(--success-color, #4caf50);
  }

  .r-xtrs-devstat-dot.off {
    background: var(--error-color, #f44336);
  }

  .r-xtrs-devstat-dot.unknown {
    background: var(--disabled-color, #9e9e9e);
  }

  .r-xtrs-devstat-table-wrap {
    overflow-x: auto;
  }

  .r-xtrs-devstat-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }

  .r-xtrs-devstat-table th {
    text-align: left;
    padding: 6px 8px;
    border-bottom: 2px solid var(--divider-color, rgba(0, 0, 0, 0.12));
    color: var(--secondary-text-color, #727272);
    font-weight: 500;
    white-space: nowrap;
    cursor: pointer;
    user-select: none;
  }

  .r-xtrs-devstat-table td {
    padding: 6px 8px;
    border-bottom: 1px solid var(--divider-color, rgba(0, 0, 0, 0.12));
    white-space: nowrap;
  }

  .r-xtrs-devstat-table tr.offline td {
    color: var(--secondary-text-color, #727272);
  }

  .r-xtrs-devstat-status {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }

  .r-xtrs-devstat-quality {
    display: inline-block;
    padding: 1px 6px;
    border-radius: 8px;
    font-size: 11px;
  }

  .r-xtrs-devstat-quality.strong {
    background: rgba(76, 175, 80, 0.15);
    color: var(--success-color, #4caf50);
  }

  .r-xtrs-devstat-quality.ok {
    background: rgba(255, 152, 0, 0.15);
    color: var(--warning-color, #ff9800);
  }

  .r-xtrs-devstat-quality.weak {
    background: rgba(244, 67, 54, 0.15);
    color: var(--error-color, #f44336);
  }

  .r-xtrs-devstat-hgi {
    font-family: monospace;
    font-size: 11px;
    color: var(--secondary-text-color, #727272);
  }

  .r-xtrs-devstat-empty {
    padding: 24px;
    text-align: center;
    color: var(--secondary-text-color, #727272);
  }

  .r-xtrs-devstat-error {
    padding: 12px;
    margin-bottom: 12px;
    border-radius: 8px;
    background: rgba(244, 67, 54, 0.1);
    color: var(--error-color, #f44336);
    font-size: 13px;
  }

  .r-xtrs-devstat-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;
  }

  .r-xtrs-devstat-refresh {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--secondary-text-color, #727272);
    padding: 4px;
  }

  .r-xtrs-devstat-refresh:hover {
    color: var(--primary-text-color, #212121);
  }
`;
