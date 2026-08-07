/**
 * Copyright 2025 Google LLC
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

import {Component, signal, computed} from '@angular/core';

@Component({
  selector: 'app-subtitles',
  templateUrl: './subtitles.component.html',
  styleUrls: ['./subtitles.component.scss'],
})
export class SubtitlesComponent {
  // Angular Signals state management
  readonly selectedFile = signal<File | null>(null);
  readonly youtubeUrl = signal<string>('');
  readonly subtitleFormat = signal<'vtt' | 'srt'>('vtt');
  readonly sourceLanguage = signal<string>('en-US');
  readonly burnSubtitles = signal<boolean>(false);
  readonly isProcessing = signal<boolean>(false);
  readonly processingStep = signal<
    'idle' | 'uploading' | 'transcribing' | 'formatting' | 'rendering' | 'completed'
  >('idle');
  readonly progressPercentage = signal<number>(0);
  readonly generatedVttUrl = signal<string | null>(null);
  readonly generatedSrtUrl = signal<string | null>(null);
  readonly previewVideoUrl = signal<string | null>(null);
  readonly isDraggingOver = signal<boolean>(false);

  // Computed signals
  readonly hasInput = computed(() => !!this.selectedFile() || !!this.youtubeUrl().trim());
  readonly isComplete = computed(() => this.processingStep() === 'completed');
  readonly inputSourceLabel = computed(() => {
    if (this.selectedFile()) {
      return this.selectedFile()!.name;
    }
    if (this.youtubeUrl().trim()) {
      return 'YouTube URL Source';
    }
    return 'No file or link selected';
  });

  readonly availableLanguages = [
    {code: 'en-US', label: 'English (US)'},
    {code: 'es-ES', label: 'Spanish'},
    {code: 'fr-FR', label: 'French'},
    {code: 'de-DE', label: 'German'},
    {code: 'ja-JP', label: 'Japanese'},
    {code: 'pt-BR', label: 'Portuguese (Brazil)'},
  ];

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (input.files && input.files.length > 0) {
      const file = input.files[0];
      this.selectedFile.set(file);
      this.previewVideoUrl.set(URL.createObjectURL(file));
      this.youtubeUrl.set('');
    }
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    this.isDraggingOver.set(true);
  }

  onDragLeave(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    this.isDraggingOver.set(false);
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    this.isDraggingOver.set(false);
    if (event.dataTransfer && event.dataTransfer.files.length > 0) {
      const file = event.dataTransfer.files[0];
      this.selectedFile.set(file);
      this.previewVideoUrl.set(URL.createObjectURL(file));
      this.youtubeUrl.set('');
    }
  }

  onYoutubeUrlChange(url: string): void {
    this.youtubeUrl.set(url);
    if (url.trim()) {
      this.selectedFile.set(null);
    }
  }

  setFormat(format: 'vtt' | 'srt'): void {
    this.subtitleFormat.set(format);
  }

  setLanguage(lang: string): void {
    this.sourceLanguage.set(lang);
  }

  toggleBurnSubtitles(): void {
    this.burnSubtitles.update(val => !val);
  }

  clearSelection(): void {
    this.selectedFile.set(null);
    this.youtubeUrl.set('');
    this.previewVideoUrl.set(null);
    this.processingStep.set('idle');
    this.progressPercentage.set(0);
    this.generatedVttUrl.set(null);
    this.generatedSrtUrl.set(null);
  }

  startGeneration(): void {
    if (!this.hasInput() || this.isProcessing()) return;

    this.isProcessing.set(true);
    this.processingStep.set('uploading');
    this.progressPercentage.set(15);

    setTimeout(() => {
      this.processingStep.set('transcribing');
      this.progressPercentage.set(45);
    }, 1500);

    setTimeout(() => {
      this.processingStep.set('formatting');
      this.progressPercentage.set(75);
    }, 3000);

    setTimeout(() => {
      this.processingStep.set('rendering');
      this.progressPercentage.set(90);
    }, 4500);

    setTimeout(() => {
      this.processingStep.set('completed');
      this.progressPercentage.set(100);
      this.isProcessing.set(false);
      this.generatedVttUrl.set('#download-vtt');
      this.generatedSrtUrl.set('#download-srt');
    }, 6000);
  }
}
