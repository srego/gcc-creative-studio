/**
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import {HttpClient} from '@angular/common/http';
import {Injectable} from '@angular/core';
import {Observable} from 'rxjs';
import {environment} from '../../../environments/environment';

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp?: string;
}

export interface QueryRequest {
  prompt: string;
  sessionId?: string;
  context?: Record<string, unknown>;
}

export interface QueryResponse {
  response: string;
  sessionId?: string;
  metadata?: Record<string, unknown>;
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
}

@Injectable({
  providedIn: 'root',
})
export class AdkAssistantService {
  private readonly apiUrl = `${environment.backendURL}/custom/adk-assistant`;

  constructor(private readonly http: HttpClient) {}

  checkHealth(): Observable<HealthResponse> {
    return this.http.get<HealthResponse>(`${this.apiUrl}/health`);
  }

  query(prompt: string, sessionId?: string): Observable<QueryResponse> {
    return this.http.post<QueryResponse>(`${this.apiUrl}/query`, {
      prompt,
      sessionId,
    });
  }
}
