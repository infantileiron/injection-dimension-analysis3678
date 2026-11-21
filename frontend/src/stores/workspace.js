import {request, saveFile} from '../api/http.js';
import {session} from './session.js';

const call = (path, body) => request(path, {token:session.token, body});
export const workspace = {
  spec: null,
  datasets: [],
  runs: [],
  ledgerSpec: null,
  ledgerBatches: [],
  async init() {
    this.spec = await request('/spec');
    this.ledgerSpec = await call('/ledgers/spec');
  },
  async refresh() {
    const [datasets, runs, batches] = await Promise.all([
      call('/datasets'), call('/runs'), call('/ledgers'),
    ]);
    this.datasets = datasets;
    this.runs = runs;
    this.ledgerBatches = batches;
  },
  getDataset: (id, offset = 0) => call(`/datasets/${id}?offset=${offset}`),
  getRun: id => call(`/runs/${id}`),
  upload: data => call('/datasets', data),
  start: data => call('/runs', data),
  review: (id, data) => call(`/runs/${id}/review`, data),
  audit: () => call('/audit'),
  schedules: () => call('/schedules'),
  deliveries: () => call('/deliveries'),
  schedule: data => call('/schedules', data),
  disable: id => call(`/schedules/${id}/disable`, {}),
  download: (path, filename) => saveFile(path, session.token, filename),
  ledgerPreview: data => call('/ledgers/preview', data),
  ledgerUpload: data => call('/ledgers', data),
  ledgerBatchesList: () => call('/ledgers'),
  getLedgerBatch: id => call(`/ledgers/${id}`),
  ledgerSupplement: (id, data) => call(`/ledgers/${id}/supplement`, data),
  getSnapshot: id => call(`/ledgers/snapshots/${id}`),
  startSnapshotRun: data => call(`/ledgers/snapshots/${data.snapshot_id}/runs`, data),
};
