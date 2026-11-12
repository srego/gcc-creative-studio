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

import {CommonModule, isPlatformBrowser} from '@angular/common';
import {HttpErrorResponse} from '@angular/common/http';
import {
  Component,
  OnInit,
  OnDestroy,
  signal,
  computed,
  PLATFORM_ID,
  Inject,
  DestroyRef,
  inject,
  ViewChild,
  ElementRef,
} from '@angular/core';
import {takeUntilDestroyed} from '@angular/core/rxjs-interop';
import {FormsModule} from '@angular/forms';
import {MatButtonModule} from '@angular/material/button';
import {MatDialog, MatDialogModule} from '@angular/material/dialog';
import {MatIconModule} from '@angular/material/icon';
import {MatProgressSpinnerModule} from '@angular/material/progress-spinner';
import {MatTooltipModule} from '@angular/material/tooltip';
import {ActivatedRoute, RouterModule} from '@angular/router';
import {Subscription, timer, of, throwError} from 'rxjs';
import {switchMap, catchError} from 'rxjs/operators';
import {ImageSelectorComponent} from '../../common/components/image-selector/image-selector.component';
import {WorkspaceStateService} from '../../services/workspace/workspace-state.service';
import {SubtitlesService, SubtitleResponse} from './subtitles.service';

export type InputSourceTab = 'upload' | 'gallery' | 'url';
export type SubtitleStep =
  | 'idle'
  | 'uploading'
  | 'extracting'
  | 'transcribing'
  | 'formatting'
  | 'packaging'
  | 'completed'
  | 'failed';

@Component({
  selector: 'app-subtitles',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatDialogModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
    RouterModule,
  ],
  templateUrl: './subtitles.component.html',
  styleUrls: ['./subtitles.component.scss'],
})
export class SubtitlesComponent implements OnInit, OnDestroy {
  private destroyRef = inject(DestroyRef);

  @ViewChild('burnedVideoPlayer')
  burnedVideoPlayerRef?: ElementRef<HTMLVideoElement>;
  @ViewChild('sourceVideoPlayer')
  sourceVideoPlayerRef?: ElementRef<HTMLVideoElement>;

  constructor(
    private dialog: MatDialog,
    private subtitlesService: SubtitlesService,
    private workspaceStateService: WorkspaceStateService,
    private route: ActivatedRoute,
    @Inject(PLATFORM_ID) private platformId: object,
  ) {}

  // Navigation & Input Signals
  readonly activeTab = signal<InputSourceTab>('upload');
  readonly selectedFile = signal<File | null>(null);
  readonly selectedGalleryAsset = signal<{
    id: string;
    title: string;
    url: string;
    previewUrl?: string | null;
  } | null>(null);
  readonly videoUrl = signal<string>('');

  // Configuration Signals
  readonly packageName = signal<string>('');
  readonly sourceLanguage = signal<string>('en-US');
  readonly enableDynamicSubtitles = signal<boolean>(true);
  readonly enableBurnedInVideo = signal<boolean>(true);
  readonly subtitleStylePreset = signal<'minimal' | 'tiktok' | 'box' | 'neon'>(
    'minimal',
  );

  // Processing & Step Signals
  readonly isProcessing = signal<boolean>(false);
  readonly processingStep = signal<SubtitleStep>('idle');
  readonly progressPercentage = signal<number>(0);
  readonly isDraggingOver = signal<boolean>(false);
  readonly sourceVideoPreviewUrl = signal<string | null>(null);
  readonly subtitledVideoPreviewUrl = signal<string | null>(null);
  readonly previewVideoUrl = signal<string | null>(null);
  readonly hasBurnedVideoOutput = signal<boolean>(false);
  readonly softCcEnabled = signal<boolean>(true);
  readonly parsedVttCues = signal<
    Array<{start: number; end: number; text: string}>
  >([]);
  readonly activeCueText = signal<string>('');
  readonly savedToGallery = signal<boolean>(false);
  readonly savedPackageName = signal<string>('');
  readonly localOutputDir = signal<string | null>(null);
  readonly activeJobId = signal<string | null>(null);
  readonly errorMessage = signal<string | null>(null);

  private pollSubscription?: Subscription;

  readonly statusDescription = computed(() => {
    switch (this.processingStep()) {
      case 'uploading':
        return 'Uploading source media to server...';
      case 'extracting':
        return 'Extracting high-fidelity audio stream...';
      case 'transcribing':
        return 'Transcribing speech with STT v2 chirp_3...';
      case 'formatting':
        return 'Refining formatting with Gemini (<= 42 chars/line)...';
      case 'packaging':
        return 'Embedding tracks and exporting MP4/VTT/SRT...';
      case 'completed':
        return 'Package generated successfully!';
      case 'failed':
        return 'Subtitle generation encountered an error.';
      default:
        return 'Idle';
    }
  });

  readonly availableLanguages = [
    {code: 'en-US', label: 'English (US)'},
    {code: 'es-ES', label: 'Spanish'},
    {code: 'fr-FR', label: 'French'},
    {code: 'de-DE', label: 'German'},
    {code: 'ja-JP', label: 'Japanese'},
    {code: 'pt-BR', label: 'Portuguese (Brazil)'},
  ];

  // Computed Signals
  readonly hasInput = computed(() => {
    if (this.activeTab() === 'upload') return !!this.selectedFile();
    if (this.activeTab() === 'gallery') return !!this.selectedGalleryAsset();
    if (this.activeTab() === 'url') return !!this.videoUrl().trim();
    return false;
  });

  readonly hasValidOutput = computed(() => {
    return this.enableDynamicSubtitles() || this.enableBurnedInVideo();
  });

  readonly isComplete = computed(() => this.processingStep() === 'completed');

  readonly suggestedPackageName = computed(() => {
    let baseName = 'Media Track';
    if (this.selectedFile()) {
      baseName = this.selectedFile()!.name.replace(/\.[^/.]+$/, '');
    } else if (this.selectedGalleryAsset()) {
      baseName = this.selectedGalleryAsset()!.title.replace(/\.[^/.]+$/, '');
    } else if (this.videoUrl().trim()) {
      baseName = 'Web Video';
    }
    const langCode = this.sourceLanguage().split('-')[0].toUpperCase();
    return `${baseName} - Subtitles [${langCode}]`;
  });

  readonly currentPackageDisplayName = computed(() => {
    return this.packageName().trim() || this.suggestedPackageName();
  });

  readonly vttTrackUrl = computed(() => {
    const jid = this.activeJobId();
    if (jid && this.isComplete() && this.enableDynamicSubtitles()) {
      return this.subtitlesService.getDownloadUrl(jid, 'vtt');
    }
    return null;
  });

  ngOnInit(): void {
    this.route.queryParamMap
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(params => {
        const jobId = params.get('job_id');
        const gcsUri = params.get('gcs_uri');
        const videoUrl = params.get('video_url');
        const packageName =
          params.get('package_name') || params.get('title') || '';

        if (videoUrl) {
          this.sourceVideoPreviewUrl.set(videoUrl);
          this.previewVideoUrl.set(videoUrl);
        }
        if (packageName) {
          this.packageName.set(packageName);
        }

        if (jobId) {
          this.loadExistingJob(jobId);
        } else if (videoUrl) {
          if (packageName) {
            this.processingStep.set('completed');
            this.progressPercentage.set(100);
            this.isProcessing.set(false);
            this.enableBurnedInVideo.set(true);
            this.subtitledVideoPreviewUrl.set(videoUrl);
          }
          if (gcsUri) {
            this.activeTab.set('gallery');
            this.selectedGalleryAsset.set({
              id: 'gallery_source',
              title: packageName || 'Gallery Video',
              url: videoUrl,
            });
          }
        } else if (gcsUri) {
          this.activeTab.set('gallery');
          this.selectedGalleryAsset.set({
            id: 'gallery_source',
            title: packageName || 'Gallery Video',
            url: gcsUri,
          });
        }
      });
  }

  loadExistingJob(jobId: string): void {
    this.activeJobId.set(jobId);
    this.isProcessing.set(true);
    this.processingStep.set('uploading');
    this.subtitlesService.getJobStatus(jobId).subscribe({
      next: (res: SubtitleResponse) => {
        this.activeJobId.set(res.job_id);
        if (res.status === 'completed') {
          this.enableBurnedInVideo.set(Boolean(res.burned_in_video));
          this.handleJobCompletion(res);
        } else if (res.status === 'failed') {
          this.handleJobFailure(
            res.error_message || 'Subtitle generation failed.',
          );
        } else {
          this.isProcessing.set(true);
          this.startPollingStatus(res.job_id);
        }
      },
      error: (err: HttpErrorResponse | Error | unknown) => {
        // If the browser already has previewVideoUrl from route params, remain in completed preview state
        if (this.previewVideoUrl()) {
          this.processingStep.set('completed');
          this.progressPercentage.set(100);
          this.isProcessing.set(false);
        } else {
          const detail =
            err && typeof err === 'object' && 'error' in err
              ? (err as {error?: {detail?: string}}).error?.detail
              : err instanceof Error
                ? err.message
                : 'Subtitle job not found.';
          this.handleJobFailure(detail || 'Subtitle job not found.');
        }
      },
    });
  }

  ngOnDestroy(): void {
    this.stopPolling();
    this.cleanupPreviewUrl();
  }

  private cleanupPreviewUrl(): void {
    const currentSrc = this.sourceVideoPreviewUrl();
    if (
      isPlatformBrowser(this.platformId) &&
      currentSrc &&
      currentSrc.startsWith('blob:')
    ) {
      try {
        window.URL.revokeObjectURL(currentSrc);
      } catch (err) {
        console.debug('Failed to revoke source object URL', err);
      }
    }
    const currentSub = this.subtitledVideoPreviewUrl();
    if (
      isPlatformBrowser(this.platformId) &&
      currentSub &&
      currentSub.startsWith('blob:')
    ) {
      try {
        window.URL.revokeObjectURL(currentSub);
      } catch (err) {
        console.debug('Failed to revoke subtitled object URL', err);
      }
    }
  }

  private stopPolling(): void {
    if (this.pollSubscription) {
      this.pollSubscription.unsubscribe();
      this.pollSubscription = undefined;
    }
  }

  setActiveTab(tab: InputSourceTab): void {
    this.activeTab.set(tab);
  }

  private validateFileSize(file: File): boolean {
    const maxBytes = 500 * 1024 * 1024;
    if (file.size > maxBytes) {
      const sizeMb = (file.size / (1024 * 1024)).toFixed(1);
      this.errorMessage.set(
        `Selected file (${sizeMb} MB) exceeds maximum allowed size of 500 MB.`,
      );
      return false;
    }
    this.errorMessage.set(null);
    return true;
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (input.files && input.files.length > 0) {
      const file = input.files[0];
      if (!this.validateFileSize(file)) {
        input.value = '';
        return;
      }
      this.cleanupPreviewUrl();
      this.selectedFile.set(file);
      const objUrl = isPlatformBrowser(this.platformId)
        ? window.URL.createObjectURL(file)
        : '';
      this.sourceVideoPreviewUrl.set(objUrl);
      this.subtitledVideoPreviewUrl.set(null);
      this.previewVideoUrl.set(objUrl);
      this.selectedGalleryAsset.set(null);
      this.videoUrl.set('');
      input.value = '';
    }
  }

  openGallerySelector(): void {
    const dialogRef = this.dialog.open(ImageSelectorComponent, {
      width: '90vw',
      height: '80vh',
      maxWidth: '90vw',
      data: {
        mimeType: 'video/*',
        showFooter: true,
        maxSelection: 1,
      },
      panelClass: 'image-selector-dialog',
    });

    dialogRef
      .afterClosed()
      .subscribe((rawResult: Record<string, unknown> | unknown[] | null) => {
        const result = (
          Array.isArray(rawResult) ? rawResult[0] : rawResult
        ) as Record<string, unknown> | null;
        if (result) {
          let title = 'Selected Gallery Asset';
          let url = '';
          let previewUrl: string | null = null;

          if ('gcsUri' in result || 'originalFilename' in result) {
            title = String(
              result['originalFilename'] ||
                result['title'] ||
                'Media Gallery Video',
            );
            url = String(result['gcsUri'] || result['presignedUrl'] || '');
            previewUrl = String(
              result['presignedOriginalUrl'] || result['presignedUrl'] || '',
            );
          } else if (
            'original_filename' in result &&
            result['original_filename']
          ) {
            title = String(result['original_filename']);
            url = String(result['gcs_uri'] || result['url'] || '');
            previewUrl = String(result['presigned_url'] || result['url'] || '');
          } else if ('mediaItem' in result && result['mediaItem']) {
            const item = result['mediaItem'] as Record<string, unknown>;
            const idx =
              typeof result['selectedIndex'] === 'number'
                ? result['selectedIndex']
                : 0;
            const titles = Array.isArray(item['titles'])
              ? (item['titles'] as string[])
              : [];
            const gcsUris = Array.isArray(item['gcsUris'])
              ? (item['gcsUris'] as string[])
              : [];
            const presignedUrls = Array.isArray(item['presignedUrls'])
              ? (item['presignedUrls'] as string[])
              : [];
            title = String(
              titles[idx] ||
                item['title'] ||
                item['filename'] ||
                item['prompt'] ||
                'Gallery Video',
            );
            url = String(
              gcsUris[idx] ||
                gcsUris[0] ||
                item['gcs_uri'] ||
                item['url'] ||
                presignedUrls[idx] ||
                '',
            );
            previewUrl = String(
              presignedUrls[idx] ||
                presignedUrls[0] ||
                item['presigned_url'] ||
                item['url'] ||
                '',
            );
          } else if (typeof result === 'object' && result['title']) {
            title = String(result['title']);
            url = String(
              result['gcsUri'] || result['gcs_uri'] || result['url'] || '',
            );
            previewUrl = String(
              result['presignedUrl'] || result['url'] || '',
            );
          }

          if (url) {
            this.selectGalleryAsset({
              id: String(result['id'] || 'gallery-selected'),
              title: title || 'Media Gallery Video',
              url,
              previewUrl:
                previewUrl && previewUrl.startsWith('http')
                  ? previewUrl
                  : this.toBrowserPreviewUrl(url),
            });
          } else {
            this.errorMessage.set(
              'Selected asset does not contain a playable video URL.',
            );
          }
        }
      });
  }

  private toBrowserPreviewUrl(rawUrl: string | null | undefined): string | null {
    if (!rawUrl) return null;
    const trimmed = rawUrl.trim();
    if (!trimmed) return null;
    if (trimmed.startsWith('blob:')) return trimmed;
    if (trimmed.startsWith('gs://')) {
      const withoutScheme = trimmed.slice(5);
      const slashIdx = withoutScheme.indexOf('/');
      if (slashIdx <= 0) return null;
      const bucket = withoutScheme.slice(0, slashIdx);
      const objectPath = withoutScheme
        .slice(slashIdx + 1)
        .split('/')
        .map(seg => encodeURIComponent(seg))
        .join('/');
      return `https://storage.googleapis.com/${bucket}/${objectPath}`;
    }
    if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
      const lower = trimmed.toLowerCase();
      if (
        lower.includes('youtube.com/watch') ||
        lower.includes('youtu.be/') ||
        lower.includes('youtube.com/shorts/')
      ) {
        return null;
      }
      return trimmed;
    }
    return null;
  }

  selectGalleryAsset(asset: {
    id: string;
    title: string;
    url: string;
    previewUrl?: string | null;
  }): void {
    this.cleanupPreviewUrl();
    const resolvedPreview =
      asset.previewUrl || this.toBrowserPreviewUrl(asset.url);
    this.selectedGalleryAsset.set(asset);
    this.sourceVideoPreviewUrl.set(resolvedPreview);
    this.subtitledVideoPreviewUrl.set(null);
    this.previewVideoUrl.set(resolvedPreview);
    this.selectedFile.set(null);
    this.videoUrl.set('');
  }

  onUrlChange(url: string): void {
    this.videoUrl.set(url);
    if (url.trim()) {
      this.cleanupPreviewUrl();
      this.selectedFile.set(null);
      this.selectedGalleryAsset.set(null);
      const browserUrl = this.toBrowserPreviewUrl(url);
      this.sourceVideoPreviewUrl.set(browserUrl);
      this.subtitledVideoPreviewUrl.set(null);
      this.previewVideoUrl.set(browserUrl);
    } else {
      this.sourceVideoPreviewUrl.set(null);
      this.previewVideoUrl.set(null);
    }
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    this.isDraggingOver.set(true);
  }

  onDragLeave(event: DragEvent): void {
    event.preventDefault();
    this.isDraggingOver.set(false);
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    this.isDraggingOver.set(false);
    if (event.dataTransfer && event.dataTransfer.files.length > 0) {
      const file = event.dataTransfer.files[0];
      if (!this.validateFileSize(file)) {
        return;
      }
      this.cleanupPreviewUrl();
      this.selectedFile.set(file);
      const objUrl = isPlatformBrowser(this.platformId)
        ? window.URL.createObjectURL(file)
        : '';
      this.sourceVideoPreviewUrl.set(objUrl);
      this.subtitledVideoPreviewUrl.set(null);
      this.previewVideoUrl.set(objUrl);
      this.selectedGalleryAsset.set(null);
      this.videoUrl.set('');
    }
  }

  toggleDynamicSubtitles(): void {
    this.enableDynamicSubtitles.update(val => !val);
  }

  toggleBurnedInVideo(): void {
    this.enableBurnedInVideo.update(val => !val);
  }

  setLanguage(lang: string): void {
    this.sourceLanguage.set(lang);
  }

  setStylePreset(preset: 'minimal' | 'tiktok' | 'box' | 'neon'): void {
    this.subtitleStylePreset.set(preset);
  }

  clearSelection(): void {
    this.resetStudio();
  }

  resetStudio(): void {
    this.stopPolling();
    this.cleanupPreviewUrl();
    this.selectedFile.set(null);
    this.selectedGalleryAsset.set(null);
    this.videoUrl.set('');
    this.packageName.set('');
    this.sourceVideoPreviewUrl.set(null);
    this.subtitledVideoPreviewUrl.set(null);
    this.previewVideoUrl.set(null);
    this.hasBurnedVideoOutput.set(false);
    this.softCcEnabled.set(true);
    this.parsedVttCues.set([]);
    this.activeCueText.set('');
    this.processingStep.set('idle');
    this.progressPercentage.set(0);
    this.isProcessing.set(false);
    this.savedToGallery.set(false);
    this.savedPackageName.set('');
    this.localOutputDir.set(null);
    this.activeJobId.set(null);
    this.errorMessage.set(null);
  }

  startGeneration(): void {
    if (!this.hasInput() || !this.hasValidOutput() || this.isProcessing())
      return;

    this.stopPolling();
    this.isProcessing.set(true);
    this.processingStep.set('uploading');
    this.progressPercentage.set(10);
    this.savedToGallery.set(false);
    this.errorMessage.set(null);

    const videoSource =
      this.activeTab() === 'gallery'
        ? this.selectedGalleryAsset()?.url
        : this.activeTab() === 'url'
          ? this.videoUrl()
          : undefined;

    const file = this.activeTab() === 'upload' ? this.selectedFile() : null;

    this.subtitlesService
      .generateSubtitles({
        file,
        videoUrl: videoSource,
        packageName: this.currentPackageDisplayName(),
        languageCode: this.sourceLanguage(),
        outputFormat: 'vtt',
        burnSubtitles: this.enableBurnedInVideo(),
        stylePreset: this.subtitleStylePreset(),
      })
      .subscribe({
        next: (initRes: SubtitleResponse) => {
          this.activeJobId.set(initRes.job_id);
          this.localOutputDir.set(initRes.local_output_dir || null);

          if (initRes.status === 'completed') {
            this.handleJobCompletion(initRes);
            return;
          }

          if (initRes.status === 'failed') {
            this.handleJobFailure(
              initRes.error_message || 'Subtitle processing failed.',
            );
            return;
          }

          this.processingStep.set(
            (initRes.step as SubtitleStep) || 'extracting',
          );
          this.progressPercentage.set(initRes.progress || 15);
          this.startPollingStatus(initRes.job_id);
        },
        error: (err: HttpErrorResponse | Error | unknown) => {
          const detail =
            err && typeof err === 'object' && 'error' in err
              ? (err as {error?: {detail?: string}}).error?.detail
              : err instanceof Error
                ? err.message
                : 'Failed to submit subtitle job.';
          this.handleJobFailure(detail || 'Failed to submit subtitle job.');
        },
      });
  }

  private startPollingStatus(jobId: string): void {
    this.stopPolling();
    let consecutiveErrors = 0;

    this.pollSubscription = timer(0, 1500)
      .pipe(
        switchMap(() =>
          this.subtitlesService.getJobStatus(jobId).pipe(
            catchError(err => {
              consecutiveErrors++;
              if (consecutiveErrors >= 8) {
                return throwError(() => err);
              }
              return of(null);
            }),
          ),
        ),
      )
      .subscribe({
        next: (res: SubtitleResponse | null) => {
          if (!res) return;
          consecutiveErrors = 0;

          if (res.status === 'completed') {
            this.stopPolling();
            this.handleJobCompletion(res);
          } else if (res.status === 'failed') {
            this.stopPolling();
            this.handleJobFailure(
              res.error_message || 'Subtitle generation failed.',
            );
          } else {
            if (res.step) {
              this.processingStep.set(res.step as SubtitleStep);
            }
            if (typeof res.progress === 'number') {
              this.progressPercentage.set(res.progress);
            }
          }
        },
        error: (err: HttpErrorResponse | Error | unknown) => {
          this.stopPolling();
          const detail =
            err && typeof err === 'object' && 'error' in err
              ? (err as {error?: {detail?: string}}).error?.detail
              : err instanceof Error
                ? err.message
                : 'Lost connection to subtitle tracking service.';
          this.handleJobFailure(
            detail || 'Lost connection to subtitle tracking service.',
          );
        },
      });
  }

  toggleSoftCc(): void {
    this.softCcEnabled.update(val => !val);
  }

  onOutputVideoTimeUpdate(event: Event): void {
    const videoEl = event.target as HTMLVideoElement | null;
    if (!videoEl || this.hasBurnedVideoOutput() || !this.softCcEnabled()) {
      this.activeCueText.set('');
      return;
    }
    const t = videoEl.currentTime;
    const cues = this.parsedVttCues();
    for (const cue of cues) {
      if (t >= cue.start && t <= cue.end) {
        if (this.activeCueText() !== cue.text) {
          this.activeCueText.set(cue.text);
        }
        return;
      }
    }
    if (this.activeCueText()) {
      this.activeCueText.set('');
    }
  }

  private parseVttTime(ts: string): number {
    const clean = ts.trim().replace(',', '.');
    const parts = clean.split(':');
    if (parts.length === 3) {
      return (
        parseFloat(parts[0]) * 3600 +
        parseFloat(parts[1]) * 60 +
        parseFloat(parts[2])
      );
    }
    if (parts.length === 2) {
      return parseFloat(parts[0]) * 60 + parseFloat(parts[1]);
    }
    return 0;
  }

  private parseWebVtt(
    vttContent: string,
  ): Array<{start: number; end: number; text: string}> {
    const blocks = vttContent.replace(/\r\n/g, '\n').split(/\n\s*\n/);
    const cues: Array<{start: number; end: number; text: string}> = [];
    for (const block of blocks) {
      const lines = block
        .split('\n')
        .map(l => l.trim())
        .filter(Boolean);
      if (!lines.length || lines[0].startsWith('WEBVTT')) continue;
      const arrowLineIdx = lines.findIndex(l => l.includes('-->'));
      if (arrowLineIdx === -1) continue;
      const [rawStart, rawEndWithSettings] = lines[arrowLineIdx].split('-->');
      const rawEnd = (rawEndWithSettings || '').trim().split(/\s+/)[0];
      const start = this.parseVttTime(rawStart);
      const end = this.parseVttTime(rawEnd);
      const text = lines.slice(arrowLineIdx + 1).join('\n').trim();
      if (text && end >= start) {
        cues.push({start, end, text});
      }
    }
    return cues;
  }

  private loadSoftSubtitleCues(jobId: string): void {
    this.subtitlesService.downloadFile(jobId, 'vtt').subscribe({
      next: async blob => {
        try {
          const text = await blob.text();
          this.parsedVttCues.set(this.parseWebVtt(text));
        } catch (e) {
          console.warn('Failed to parse WebVTT cues for preview:', e);
        }
      },
      error: err => {
        console.warn('Could not load WebVTT cues for dynamic preview:', err);
      },
    });
  }

  private fetchAuthenticatedVideoBlobUrl(
    jobId: string,
    fileType: 'burned_in_video' | 'toggleable_video' | 'source_video',
    targetSignal: typeof this.sourceVideoPreviewUrl,
    playerRef?: ElementRef<HTMLVideoElement>,
  ): void {
    if (!isPlatformBrowser(this.platformId)) return;
    this.subtitlesService.downloadFile(jobId, fileType).subscribe({
      next: blob => {
        const objUrl = window.URL.createObjectURL(blob);
        targetSignal.set(objUrl);
        setTimeout(() => {
          playerRef?.nativeElement?.load();
        }, 50);
      },
      error: err => {
        console.warn(`Authenticated fallback fetch for ${fileType} failed:`, err);
      },
    });
  }

  private handleJobCompletion(res: SubtitleResponse): void {
    this.processingStep.set('completed');
    this.progressPercentage.set(100);
    this.isProcessing.set(false);
    this.localOutputDir.set(res.local_output_dir || null);

    if (res.job_id) {
      this.activeJobId.set(res.job_id);
      const burnedGenerated = Boolean(
        res.burned_in_video && this.enableBurnedInVideo(),
      );
      this.hasBurnedVideoOutput.set(burnedGenerated);
      this.activeCueText.set('');

      // 1. Source Media Preview: always prefer the backend V4 presigned source_video_path
      // unless the user already has a local File blob: URL loaded in memory.
      const existingSource = this.sourceVideoPreviewUrl();
      if (!existingSource || !existingSource.startsWith('blob:')) {
        if (res.source_video_path && res.source_video_path.startsWith('http')) {
          this.sourceVideoPreviewUrl.set(res.source_video_path);
        } else {
          this.fetchAuthenticatedVideoBlobUrl(
            res.job_id,
            'source_video',
            this.sourceVideoPreviewUrl,
            this.sourceVideoPlayerRef,
          );
        }
      }

      // 2. Output Preview: Burned-In MP4 when generated, or Dynamic Soft-Subtitle Preview otherwise
      let streamUrl: string | null = null;
      if (burnedGenerated) {
        this.parsedVttCues.set([]);
        if (res.burned_in_video && res.burned_in_video.startsWith('http')) {
          streamUrl = res.burned_in_video;
        } else if (
          res.processed_video_url &&
          res.processed_video_url.startsWith('http')
        ) {
          streamUrl = res.processed_video_url;
        }
      } else if (this.enableDynamicSubtitles()) {
        this.softCcEnabled.set(true);
        this.loadSoftSubtitleCues(res.job_id);
        if (
          res.default_toggleable_video &&
          res.default_toggleable_video.startsWith('http')
        ) {
          streamUrl = res.default_toggleable_video;
        } else if (
          res.source_video_path &&
          res.source_video_path.startsWith('http')
        ) {
          streamUrl = res.source_video_path;
        } else if (existingSource && existingSource.startsWith('blob:')) {
          streamUrl = existingSource;
        }
      }

      if (streamUrl) {
        this.subtitledVideoPreviewUrl.set(streamUrl);
        this.previewVideoUrl.set(streamUrl);
      } else if (burnedGenerated || this.enableDynamicSubtitles()) {
        this.fetchAuthenticatedVideoBlobUrl(
          res.job_id,
          burnedGenerated ? 'burned_in_video' : 'toggleable_video',
          this.subtitledVideoPreviewUrl,
          this.burnedVideoPlayerRef,
        );
      }

      setTimeout(() => {
        if (isPlatformBrowser(this.platformId)) {
          if (this.burnedVideoPlayerRef?.nativeElement) {
            this.burnedVideoPlayerRef.nativeElement.load();
          }
          if (this.sourceVideoPlayerRef?.nativeElement) {
            this.sourceVideoPlayerRef.nativeElement.load();
          }
        }
      }, 50);
    }
  }

  private handleJobFailure(errorMsg: string): void {
    this.processingStep.set('failed');
    this.isProcessing.set(false);
    this.errorMessage.set(errorMsg);
  }

  onBurnedVideoError(event: Event): void {
    const currentUrl = this.subtitledVideoPreviewUrl();
    const jid = this.activeJobId();
    if (jid && currentUrl && !currentUrl.startsWith('blob:')) {
      console.warn(
        'Output video stream playback error, attempting authenticated blob fallback',
        event,
      );
      this.fetchAuthenticatedVideoBlobUrl(
        jid,
        this.hasBurnedVideoOutput() ? 'burned_in_video' : 'toggleable_video',
        this.subtitledVideoPreviewUrl,
        this.burnedVideoPlayerRef,
      );
    } else {
      console.warn('Output video stream error event received:', event);
    }
  }

  onSourceVideoError(event: Event): void {
    const currentUrl = this.sourceVideoPreviewUrl();
    const jid = this.activeJobId();
    if (jid && currentUrl && !currentUrl.startsWith('blob:')) {
      console.warn(
        'Source video stream playback error, attempting authenticated blob fallback',
        event,
      );
      this.fetchAuthenticatedVideoBlobUrl(
        jid,
        'source_video',
        this.sourceVideoPreviewUrl,
        this.sourceVideoPlayerRef,
      );
    }
  }

  readonly isSavingToGallery = signal<boolean>(false);
  readonly savedAssetId = signal<number | null>(null);
  readonly savedItemsCount = signal<number>(0);
  readonly savedFilenames = signal<string[]>([]);
  readonly isDownloadingFile = signal<string | null>(null);

  private triggerBrowserDownload(blob: Blob, filename: string): void {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      if (document.body.contains(a)) {
        document.body.removeChild(a);
      }
      window.URL.revokeObjectURL(url);
    }, 2000);
  }

  downloadCaptions(type: 'vtt' | 'srt'): void {
    const jobId = this.activeJobId();
    if (
      !jobId ||
      !isPlatformBrowser(this.platformId) ||
      this.isDownloadingFile()
    )
      return;

    this.isDownloadingFile.set(type);
    this.subtitlesService.downloadFile(jobId, type).subscribe({
      next: blob => {
        this.isDownloadingFile.set(null);
        this.triggerBrowserDownload(
          blob,
          `${this.currentPackageDisplayName()}.${type}`,
        );
      },
      error: async err => {
        this.isDownloadingFile.set(null);
        let msg = err?.message || 'Server error';
        if (err?.error instanceof Blob) {
          try {
            const parsed = JSON.parse(await err.error.text());
            msg = parsed?.detail || msg;
          } catch {
            // fallback
          }
        }
        this.errorMessage.set(`Failed to download .${type} file: ${msg}`);
      },
    });
  }

  downloadVideo(): void {
    const jobId = this.activeJobId();
    if (
      !jobId ||
      !isPlatformBrowser(this.platformId) ||
      this.isDownloadingFile()
    )
      return;

    this.isDownloadingFile.set('video');
    const fileType = this.enableBurnedInVideo()
      ? 'burned_in_video'
      : 'toggleable_video';
    this.subtitlesService.downloadFile(jobId, fileType).subscribe({
      next: blob => {
        this.isDownloadingFile.set(null);
        const suffix = this.enableBurnedInVideo() ? ' (Burned)' : '';
        this.triggerBrowserDownload(
          blob,
          `${this.currentPackageDisplayName()}${suffix}.mp4`,
        );
      },
      error: async err => {
        this.isDownloadingFile.set(null);
        let msg = err?.message || 'Server error';
        if (err?.error instanceof Blob) {
          try {
            const parsed = JSON.parse(await err.error.text());
            msg = parsed?.detail || msg;
          } catch {
            // fallback
          }
        }
        this.errorMessage.set(`Failed to download MP4 video: ${msg}`);
      },
    });
  }

  saveToMediaGallery(): void {
    const jobId = this.activeJobId();
    if (!jobId || this.isSavingToGallery()) return;

    const pkgName = this.currentPackageDisplayName();
    const rawWorkspaceId = this.workspaceStateService.getActiveWorkspaceId();
    const workspaceId = rawWorkspaceId ? Number(rawWorkspaceId) : null;

    this.isSavingToGallery.set(true);
    this.subtitlesService.saveToGallery(jobId, workspaceId, pkgName).subscribe({
      next: res => {
        this.isSavingToGallery.set(false);
        this.savedPackageName.set(res.asset_name || pkgName);
        this.savedAssetId.set(res.asset_id ?? null);
        this.savedItemsCount.set(res.saved_items_count || 1);
        this.savedFilenames.set(res.saved_filenames || []);
        this.savedToGallery.set(true);
      },
      error: err => {
        this.isSavingToGallery.set(false);
        const detail =
          err && typeof err === 'object' && 'error' in err
            ? (err as {error?: {detail?: string}}).error?.detail
            : err instanceof Error
              ? err.message
              : 'Failed to save creation to Media Gallery.';
        this.errorMessage.set(
          detail || 'Failed to save creation to Media Gallery.',
        );
      },
    });
  }
}
