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

import {Routes} from '@angular/router';
import {AuthGuardService} from '../common/services/auth.guard.service';
import {AdkAssistantComponent} from './adk_assistant/adk-assistant.component';
import {SubtitlesComponent} from './subtitles/subtitles.component';

export interface CustomToolEntry {
  slug: string;
  label: string;
  icon: string;
  route: string;
  description?: string;
}

/**
 * Declarative registry of custom modules displayed inside the Custom Tools
 * (`person` icon) flyout drawer in `header.component.html`.
 *
 * To remove the default Closed Captioning (`subtitles`) tool or add new custom
 * tools, edit only this registry—core files (`header.component.*` and
 * `app-routing.module.ts`) never need to be modified per module.
 */
export const CUSTOM_TOOLS: CustomToolEntry[] = [
  {
    slug: 'subtitles',
    label: 'Video Subtitles',
    icon: 'subtitles',
    route: '/custom/subtitles',
    description: 'Chirp 3 + Gemini Flash closed captioning and subtitle burn-in',
  },
  {
    slug: 'adk-assistant',
    label: 'ADK Assistant',
    icon: 'auto_awesome',
    route: '/custom/adk-assistant',
    description: 'ADK multimodal creative prompt and storyboard assistant',
  },
];

export const CUSTOM_ROUTES: Routes = [
  {
    path: 'custom/subtitles',
    component: SubtitlesComponent,
    canActivate: [AuthGuardService],
  },
  {
    path: 'custom/adk-assistant',
    component: AdkAssistantComponent,
    canActivate: [AuthGuardService],
  },
];
