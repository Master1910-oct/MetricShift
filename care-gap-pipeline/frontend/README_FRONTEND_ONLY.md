# Metric Shift Frontend

Frontend-only extraction from the supplied Star Rating Optimization project.

## Stack
- React + TypeScript
- Vite
- React Router
- Axios
- Recharts
- Lucide React

## Run
npm install
npm run dev

## Integration
The existing `src/api/client.ts` contains the original project's API contract. Replace/adapt these API calls to the new FastAPI backend created around the current Metric Shift pipeline.

Do not move ML, Rule Engine, optimizer, or model files into this frontend.
