import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
});

export interface PipelineStageState {
  status: 'pending' | 'running' | 'completed' | 'failed';
  message: string;
  rows?: number | null;
  error?: string | null;
}

export interface PipelineJob {
  run_id?: string;
  job_id?: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | string;
  error: string | null;
  stages: {
    file_upload?: PipelineStageState;
    rule_engine?: PipelineStageState;
    candidate_generation?: PipelineStageState;
    ml_inference?: PipelineStageState;
    calibration?: PipelineStageState;
    intervention_selection?: PipelineStageState;
    milp_optimization?: PipelineStageState;
    star_rating_contribution?: PipelineStageState;
    final_report?: PipelineStageState;
    [key: string]: PipelineStageState | undefined;
  };
}

export interface DashboardMetrics {
  summary: {
    total_plans: number;
    total_members: number;
    open_care_gaps: number;
    cms_measures: number;
    selected_members?: number;
    avg_closure_probability?: number;
    total_star_contribution?: number;
  };
  gaps_by_plan: { plan_id: string; gaps: number }[];
  plan_performances: { plan_id: string; plan_name: string; rating: number }[];
  improvement_trend: { year: number; rating: number }[];
  intervention_distribution?: { name: string; value: number }[];
  care_gap_distribution?: { name: string; value: number }[];
}

export interface PlanDetails {
  summary: {
    total_members: number;
    open_care_gaps: number;
    total_care_gaps: number;
    plan_rating: number;
    selected_members?: number;
  };
  gaps_by_status: { name: string; value: number }[];
  resolved_over_time?: { year: number; resolved: number }[];
  improvement_trend: { year: number; rating: number }[];
  details: {
    plan_id: string;
    plan_name: string;
    contract_id: string;
    plan_type: string;
    county: string;
    rating_year: number;
    start_date: string;
  };
  measures?: {
    measure_id: string;
    performance_value: number;
    measure_star: number;
    weight: number;
  }[];
}

export interface MemberRecord {
  member_id: string;
  member_name: string;
  dob: string;
  age: number;
  gender: string;
  condition: string;
  plan_id: string;
  care_gaps?: string;
  recommended_intervention?: string;
  gap_status?: string;
  star_contribution?: string;
}

export interface MembersResponse {
  records: MemberRecord[];
  pagination: {
    total_records: number;
    page: number;
    limit: number;
    total_pages: number;
  };
}

export interface MemberDetails {
  member_id: string;
  member_name: string;
  overall_priority: 'High' | 'Medium' | 'Low';
  priority_score: number;
  details: {
    health_plan: string;
    dob: string;
    age: number;
    gender: string;
    conditions: string;
    enrollment_date: string;
    plan_type: string;
  };
  gaps_summary: {
    open_care_gaps: number;
    closed_care_gaps: number;
    high_priority_gaps: number;
  };
  care_gaps: {
    care_gap_name: string;
    measure_id: string;
    status: 'Open' | 'Closed';
  }[];
  recommended_intervention?: string;
  closure_probability?: number;
  star_contribution?: string;
}

export interface CMSMeasuresResponse {
  summary: {
    total_measures: number;
    high_priority_measures: number;
    rating_year: number;
  };
  records: {
    part: string;
    measure_id: string;
    measure_name: string;
    measure_type: string;
    domain: string;
    measure_id_value: string;
    description: string;
    weight?: number;
    performance_value?: number | null;
    measure_star?: number | null;
  }[];
}

export interface OptimizationRecord {
  s_no: number;
  member_id: string;
  member_name: string;
  age: number;
  gender: string;
  gap_count: number;
  care_gaps: string;
  recommended_intervention: string;
  gap_status: string;
  contribution: string;
}

export interface OptimizationResponse {
  records: OptimizationRecord[];
  summary: {
    total_selected: number;
    total_gaps: number;
    intervention_breakdown?: Record<string, number>;
    avg_closure_probability?: number;
  };
}

export interface PlanStateDetail {
  plan_id: string;
  plan_name: string;
  members: number;
  care_gaps: number;
  star_rating: number;
}

export interface StateLocationData {
  state_code: string;
  state_name: string;
  total_plans: number;
  total_members: number;
  open_care_gaps: number;
  closed_care_gaps: number;
  average_rating: number;
  resolution_rate: string;
  plans: PlanStateDetail[];
}

export type LocationsResponse = Record<string, StateLocationData>;

export interface UploadResponseData {
  job_id: string;
  status: string;
  mode?: 'initial' | 'member_update';
  message?: string;
  affected_members?: number;
}

// --- API FUNCTIONS ---

export const uploadDataset = async (
  file: File,
  mode: 'initial' | 'member_update' = 'initial'
): Promise<UploadResponseData> => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await apiClient.post<UploadResponseData>(`/api/upload?mode=${mode}`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
};

export const uploadInitialDataset = async (file: File): Promise<UploadResponseData> => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await apiClient.post<UploadResponseData>('/api/dataset/initial-upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
};

export const uploadMemberUpdate = async (file: File): Promise<UploadResponseData> => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await apiClient.post<UploadResponseData>('/api/dataset/member-update', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
};

export const getPipelineStatus = async (jobId: string): Promise<PipelineJob> => {
  const response = await apiClient.get<PipelineJob>(`/api/pipeline/${jobId}`);
  return response.data;
};

export const getDashboardData = async (jobId: string, planId?: string): Promise<DashboardMetrics> => {
  const params = planId ? { plan_id: planId } : {};
  const response = await apiClient.get<DashboardMetrics>(`/api/dashboard/${jobId}`, { params });
  return response.data;
};

export const getPlanData = async (jobId: string, planId: string): Promise<PlanDetails> => {
  const response = await apiClient.get<PlanDetails>(`/api/plans/${jobId}/${planId}`);
  return response.data;
};

export const listMembers = async (
  jobId: string,
  params: {
    page: number;
    limit: number;
    search?: string;
    plan_id?: string;
    gender?: string;
    min_age?: number;
    max_age?: number;
  }
): Promise<MembersResponse> => {
  const response = await apiClient.get<MembersResponse>(`/api/members/${jobId}`, { params });
  return response.data;
};

export const getMemberDetails = async (jobId: string, memberId: string): Promise<MemberDetails> => {
  const response = await apiClient.get<MemberDetails>(`/api/members/${jobId}/${memberId}`);
  return response.data;
};

export const listMeasures = async (jobId: string): Promise<CMSMeasuresResponse> => {
  const response = await apiClient.get<CMSMeasuresResponse>(`/api/measures/${jobId}`);
  return response.data;
};

export interface PlanListItem {
  plan_id: string;
  plan_name: string;
  rating: number;
  plan_type?: string;
  state?: string;
}

export interface PipelineRunItem {
  id: string;
  status: string;
  trigger_type: string;
  source_file_name?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  error_message?: string | null;
  created_at?: string | null;
}

export const getPlans = async (jobId: string): Promise<PlanListItem[]> => {
  const response = await apiClient.get<PlanListItem[]>(`/api/plans/${jobId}`);
  return response.data;
};

export const getOptimizationResults = async (jobId: string, planId: string = ''): Promise<OptimizationResponse> => {
  const params = planId ? { plan_id: planId } : {};
  const response = await apiClient.get<OptimizationResponse>(`/api/optimization/${jobId}`, { params });
  return response.data;
};

export const getLatestRun = async (): Promise<PipelineRunItem> => {
  const response = await apiClient.get<PipelineRunItem>('/api/runs/latest');
  return response.data;
};

export const listRuns = async (): Promise<PipelineRunItem[]> => {
  const response = await apiClient.get<PipelineRunItem[]>('/api/runs');
  return response.data;
};

export const getLocationsData = async (jobId: string): Promise<LocationsResponse> => {
  const response = await apiClient.get<LocationsResponse>(`/api/location/${jobId}`);
  return response.data;
};

export const getDownloadUrl = (jobId: string): string => {
  return `${API_BASE_URL}/api/download/${jobId}`;
};
