---
name: video_generation
description: Create videos using Remotion — prompt-to-video, code-based animations, compositing, and rendering. Uses Remotion MCP for documentation lookup and local CLI for rendering.
---

# Video Generation with Remotion

Remotion is a framework for creating videos programmatically with React. You can generate videos from text prompts, create animations, composite scenes, and render to MP4.

## Available Tools

### 1. Documentation Lookup (via MCP)
Use `mcp__remotion_mcp__remotion_documentation` with queries like:
- "how to render a video programmatically"
- "sequence composition example"
- "audio visualization API"

### 2. Local Remotion CLI
If Remotion is installed locally:
```bash
cd /path/to/remotion-project && npx remotion render entry.tsx out.mp4
```

## Common Video Generation Workflows

### Prompt → Video
1. Analyze the user's video concept and break it down into scenes
2. For each scene, design the visual composition using `<Sequence>`, `<AbsoluteFill>`, and animation hooks
3. Assemble all scenes into a `Composition` registered via `<Composition />` or `registerRoot()`
4. Render using the CLI or programmatic API

### Video Editing & Effects
- Use `<TransitionSeries>` for transitions between clips
- Use `<spring>` or `useCurrentFrame()` for animations
- Use `<Audio>` for background music and sound effects
- Use `<Img>` and `<Video>` for media assets

### Text & Typography
- Use `<IFrameFont>` or Google Fonts import for custom typography
- Animate text with opacity, translateY, scale transformations
- Use `<@remotion/layout-utils>` for text measurement and layout

## Remotion MCP Query Examples

The MCP provides documentation search. Use specific, concise queries:

| Goal | Query |
|------|-------|
| Rendering | "render video programmatic API" |
| Sequences | "Sequence composition nesting" |
| Audio | "add background music audio track" |
| Transitions | "TransitionSeries between scenes" |
| Spring | "spring animation timing config" |
| Still | "generate still image from composition" |

## Example: Simple Video Composition

```tsx
import { AbsoluteFill, Sequence, useCurrentFrame, spring } from 'remotion';

export const MyVideo: React.FC = () => {
  const frame = useCurrentFrame();
  const scale = spring({ frame, fps: 30 });

  return (
    <AbsoluteFill style={{ backgroundColor: 'white' }}>
      <Sequence from={0} durationInFrames={30}>
        <h1 style={{ transform: `scale(${scale})` }}>Hello</h1>
      </Sequence>
      <Sequence from={30}>
        <p>World</p>
      </Sequence>
    </AbsoluteFill>
  );
};
```

## When to Use

- User asks to create/generate/make a video
- User wants animation or motion graphics
- User needs video compositing, editing, or rendering
- User wants to turn a script/story into a video
- User needs programmatic video generation
