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

export type InputSourceTab = 'upload' | 'gallery' | 'url';

@Component({
  selector: 'app-subtitles',
  templateUrl: './subtitles.component.html',
  styleUrls: ['./subtitles.component.scss'],
})
export class SubtitlesComponent {
  // Navigation & Input Signals
  readonly activeTab = signal<InputSourceTab>('upload');
  readonly selectedFile = signal<File | null>(null);
  readonly selectedGalleryAsset = signal<{id: string; title: string; url: string} | null>(null);
  readonly videoUrl = signal<string>('');

  // Configuration Signals
  readonly packageName = signal<string>('');
  readonly sourceLanguage = signal<string>('en-US');
  readonly enableDynamicSubtitles = signal<boolean>(true);
  readonly enableBurnedInVideo = signal<boolean>(false);
  readonly subtitleStylePreset = signal<'minimal' | 'tiktok' | 'box' | 'neon'>('minimal');

  // Processing & Step Signals
  readonly isProcessing = signal<boolean>(false);
  readonly processingStep = signal<
    'idle' | 'uploading' | 'transcribing' | 'formatting' | 'rendering' | 'completed'
  >('idle');
  readonly progressPercentage = signal<number>(0);
  readonly isDraggingOver = signal<boolean>(false);
  readonly previewVideoUrl = signal<string | null>(null);
  readonly savedToGallery = signal<boolean>(false);
  readonly savedPackageName = signal<string>('');

  // Mock Gallery Assets for Selection
  readonly galleryAssets = [
    {id: 'asset-1', title: 'Product Showcase Promo Video.mp4', url: 'https://storage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4'},
    {id: 'asset-2', title: 'Podcast Episode 10 - Tech Insights.mp4', url: 'https://storage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4'},
    {id: 'asset-3', title: 'Brand Guidelines Animation Overview.mp4', url: 'https://storage.googleapis.com/gtv-videos-bucket/sample/ElephantsDream.mp4'},
  ];

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

  readonly currentPackageDisplayName = computed(() => {
    if (this.packageName().trim()) {
      return this.packageName().trim();
    }
    let baseName = 'Media_Track';
    if (this.selectedFile()) {
      baseName = this.selectedFile()!.name.replace(/\.[^/.]+$/, '');
    } else if (this.selectedGalleryAsset()) {
      baseName = this.selectedGalleryAsset()!.title.replace(/\.[^/.]+$/, '');
    } else if (this.videoUrl().trim()) {
      baseName = 'Web_Video_Source';
    }
    const langCode = this.sourceLanguage().split('-')[0].toUpperCase();
    return `${baseName} - Subtitles [${langCode}]`;
  });

  setActiveTab(tab: InputSourceTab): void {
    this.activeTab.set(tab);
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (input.files && input.files.length > 0) {
      const file = input.files[0];
      this.selectedFile.set(file);
      this.previewVideoUrl.set(URL.createObjectURL(file));
      this.selectedGalleryAsset.set(null);
      this.videoUrl.set('');
      this.updateDefaultPackageName(file.name);
    }
  }

  selectGalleryAsset(asset: {id: string; title: string; url: string}): void {
    this.selectedGalleryAsset.set(asset);
    this.previewVideoUrl.set(asset.url);
    this.selectedFile.set(null);
    this.videoUrl.set('');
    this.updateDefaultPackageName(asset.title);
  }

  onUrlChange(url: string): void {
    this.videoUrl.set(url);
    if (url.trim()) {
      this.selectedFile.set(null);
      this.selectedGalleryAsset.set(null);
      this.updateDefaultPackageName('Web Video');
    }
  }

  private updateDefaultPackageName(rawName: string): void {
    const baseName = rawName.replace(/\.[^/.]+$/, '');
    const langCode = this.sourceLanguage().split('-')[0].toUpperCase();
    this.packageName.set(`${baseName} - Subtitles [${langCode}]`);
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
      this.selectedGalleryAsset.set(null);
      this.videoUrl.set('');
      this.updateDefaultPackageName(file.name);
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
    if (this.selectedFile()) {
      this.updateDefaultPackageName(this.selectedFile()!.name);
    } else if (this.selectedGalleryAsset()) {
      this.updateDefaultPackageName(this.selectedGalleryAsset()!.title);
    }
  }

  setStylePreset(preset: 'minimal' | 'tiktok' | 'box' | 'neon'): void {
    this.subtitleStylePreset.set(preset);
  }

  clearSelection(): void {
    this.selectedFile.set(null);
    this.selectedGalleryAsset.set(null);
    this.videoUrl.set('');
    this.packageName.set('');
    this.previewVideoUrl.set(null);
    this.processingStep.set('idle');
    this.progressPercentage.set(0);
    this.savedToGallery.set(false);
  }

  startGeneration(): void {
    if (!this.hasInput() || !this.hasValidOutput() || this.isProcessing()) return;

    this.isProcessing.set(true);
    this.processingStep.set('uploading');
    this.progressPercentage.set(15);
    this.savedToGallery.set(false);

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
    }, 6000);
  }

  saveToMediaGallery(): void {
    const pkgName = this.currentPackageDisplayName();
    this.savedPackageName.set(pkgName);
    this.savedToGallery.set(true);
  }
}
