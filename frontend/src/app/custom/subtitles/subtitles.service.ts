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

import {HttpClient, HttpHeaders} from '@angular/common/http';
import {Injectable} from '@angular/core';
import {Observable} from 'rxjs';
import {catchError, switchMap} from 'rxjs/operators';
import {environment} from '../../../environments/environment';

export interface SubtitleResponse {
  job_id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  subtitle_url?: string;
  processed_video_url?: string;
  transcript_text?: string;
  error_message?: string;
  default_toggleable_video?: string;
  burned_in_video?: string;
  subtitles_vtt?: string;
  subtitles_srt?: string;
  segment_count?: number;
  local_output_dir?: string;
  step?: string;
  progress?: number;
}

export interface SubtitleUploadUrlResponse {
  upload_url: string;
  gcs_uri: string;
}

export interface SubtitleGenerationParams {
  file?: File | null;
  videoUrl?: string;
  packageName?: string;
  languageCode?: string;
  outputFormat?: string;
  burnSubtitles?: boolean;
}

export interface SaveToGalleryResponse {
  success: boolean;
  asset_id?: number | null;
  asset_name: string;
  gcs_uri: string;
  thumbnail_uri?: string;
  saved_items_count?: number;
  saved_filenames?: string[];
  message: string;
}

@Injectable({
  providedIn: 'root',
})
export class SubtitlesService {
  private readonly baseUrl = `${environment.backendURL}/v1/custom/subtitles`;

  constructor(private http: HttpClient) {}

  getUploadUrl(
    filename: string,
    contentType = 'video/mp4',
    size?: number,
  ): Observable<SubtitleUploadUrlResponse> {
    return this.http.post<SubtitleUploadUrlResponse>(
      `${this.baseUrl}/generate-upload-url`,
      {
        filename,
        content_type: contentType,
        size,
      },
    );
  }

  uploadToGcs(signedUrl: string, file: File): Observable<unknown> {
    const headers = new HttpHeaders({'Content-Type': file.type || 'video/mp4'});
    return this.http.put(signedUrl, file, {headers, observe: 'response'});
  }

  generateSubtitles(
    params: SubtitleGenerationParams,
  ): Observable<SubtitleResponse> {
    if (params.file) {
      const file = params.file;
      return this.getUploadUrl(
        file.name,
        file.type || 'video/mp4',
        file.size,
      ).pipe(
        switchMap(({upload_url, gcs_uri}) => {
          return this.uploadToGcs(upload_url, file).pipe(
            switchMap(() => {
              return this.http.post<SubtitleResponse>(
                `${this.baseUrl}/generate`,
                {
                  video_uri: gcs_uri,
                  video_url: gcs_uri,
                  package_name: params.packageName || '',
                  language_code: params.languageCode || 'en-US',
                  output_format: params.outputFormat || 'vtt',
                  burn_subtitles: !!params.burnSubtitles,
                },
              );
            }),
          );
        }),
        catchError(err => {
          console.warn('GCS direct upload fallback to multipart:', err);
          const formData = new FormData();
          formData.append('file', file, file.name);
          if (params.packageName) {
            formData.append('package_name', params.packageName);
          }
          if (params.languageCode) {
            formData.append('language_code', params.languageCode);
          }
          if (params.outputFormat) {
            formData.append('output_format', params.outputFormat);
          }
          formData.append('burn_subtitles', String(!!params.burnSubtitles));

          return this.http.post<SubtitleResponse>(
            `${this.baseUrl}/generate`,
            formData,
          );
        }),
      );
    }

    return this.http.post<SubtitleResponse>(`${this.baseUrl}/generate`, {
      video_url: params.videoUrl || '',
      video_uri: params.videoUrl || '',
      package_name: params.packageName || '',
      language_code: params.languageCode || 'en-US',
      output_format: params.outputFormat || 'vtt',
      burn_subtitles: !!params.burnSubtitles,
    });
  }

  getJobStatus(jobId: string): Observable<SubtitleResponse> {
    return this.http.get<SubtitleResponse>(`${this.baseUrl}/status/${jobId}`);
  }

  getDownloadUrl(
    jobId: string,
    fileType:
      | 'vtt'
      | 'srt'
      | 'toggleable_video'
      | 'burned_in_video'
      | 'zip'
      | 'source_video' = 'burned_in_video',
  ): string {
    return `${this.baseUrl}/download/${jobId}?file_type=${fileType}`;
  }

  downloadFile(
    jobId: string,
    fileType: 'vtt' | 'srt' | 'toggleable_video' | 'burned_in_video' | 'zip',
  ): Observable<Blob> {
    return this.http.get(this.getDownloadUrl(jobId, fileType), {
      responseType: 'blob',
    });
  }

  saveToGallery(
    jobId: string,
    workspaceId?: number | null,
    title?: string,
  ): Observable<SaveToGalleryResponse> {
    return this.http.post<SaveToGalleryResponse>(
      `${this.baseUrl}/save-to-gallery`,
      {
        job_id: jobId,
        workspace_id: workspaceId || null,
        title: title || null,
      },
    );
  }
}
