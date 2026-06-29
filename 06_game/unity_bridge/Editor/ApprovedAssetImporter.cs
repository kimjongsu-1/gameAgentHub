using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

public static class ApprovedAssetImporter
{
    private const string InboxRoot = "Assets/Game/ApprovedImports";
    private const string SpriteRoot = "Assets/Game/Resources/Sprites";
    private const string AnimationRoot = "Assets/Game/Resources/Animation/Approved";

    [Serializable]
    private sealed class PivotData
    {
        public float x = 0.5f;
        public float y = 0.05f;
    }

    [Serializable]
    private sealed class ImportRequest
    {
        public int schema_version;
        public string asset_id;
        public string status;
        public string qa_status;
        public string source_file;
        public string resource_name;
        public int columns;
        public int rows;
        public int frame_count;
        public float fps;
        public bool loop;
        public float pixels_per_unit;
        public PivotData pivot;
        public string source_checksum;
    }

    [Serializable]
    private sealed class ImportReport
    {
        public string asset_id;
        public string resource_name;
        public string status;
        public string sprite_path;
        public string animation_path;
        public int imported_frames;
        public string error;
        public string created_at_utc;
    }

    [MenuItem("Tools/Game Production/Import Approved Assets")]
    public static void ImportApprovedPackages()
    {
        Directory.CreateDirectory(InboxRoot);
        Directory.CreateDirectory(SpriteRoot);
        Directory.CreateDirectory(AnimationRoot);
        string[] requestFiles = Directory.GetFiles(InboxRoot, "request.json", SearchOption.AllDirectories);
        if (requestFiles.Length == 0)
        {
            Debug.Log("No approved import requests found.");
            return;
        }

        List<ImportReport> reports = new List<ImportReport>();
        foreach (string requestFile in requestFiles.OrderBy(path => path, StringComparer.Ordinal))
            reports.Add(ImportOne(requestFile));

        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();
        WriteReports(reports);
        if (reports.Any(report => report.status != "SUCCESS"))
            throw new InvalidOperationException("One or more approved assets failed to import. Check Build/Reports.");
    }

    private static ImportReport ImportOne(string requestFile)
    {
        ImportRequest request = null;
        ImportReport report = new ImportReport { status = "FAILED", created_at_utc = DateTime.UtcNow.ToString("O") };
        try
        {
            request = JsonUtility.FromJson<ImportRequest>(File.ReadAllText(requestFile));
            ValidateRequest(request);
            report.asset_id = request.asset_id;
            report.resource_name = request.resource_name;

            string packageDirectory = Path.GetDirectoryName(requestFile);
            string sourcePath = Path.GetFullPath(Path.Combine(packageDirectory, request.source_file));
            string packageRoot = Path.GetFullPath(packageDirectory) + Path.DirectorySeparatorChar;
            if (!sourcePath.StartsWith(packageRoot, StringComparison.OrdinalIgnoreCase) || !File.Exists(sourcePath))
                throw new InvalidOperationException("Source PNG must exist inside its approved package.");

            string spritePath = $"{SpriteRoot}/{request.resource_name}.png";
            File.Copy(sourcePath, spritePath, true);
            AssetDatabase.ImportAsset(spritePath, ImportAssetOptions.ForceSynchronousImport);
            ConfigureSpriteSheet(spritePath, request);
            string animationPath = CreateAnimationClip(spritePath, request);

            report.status = "SUCCESS";
            report.sprite_path = spritePath;
            report.animation_path = animationPath;
            report.imported_frames = request.frame_count;
        }
        catch (Exception exception)
        {
            report.asset_id = request != null ? request.asset_id : Path.GetFileName(Path.GetDirectoryName(requestFile));
            report.error = exception.Message;
            Debug.LogError($"Approved asset import failed: {requestFile}\n{exception}");
        }
        return report;
    }

    private static void ValidateRequest(ImportRequest request)
    {
        if (request == null || request.schema_version != 1)
            throw new InvalidOperationException("Unsupported import request schema.");
        if (request.status != "APPROVED" || request.qa_status != "PASS")
            throw new InvalidOperationException("Asset must be APPROVED and QA PASS.");
        if (string.IsNullOrWhiteSpace(request.asset_id) || string.IsNullOrWhiteSpace(request.resource_name))
            throw new InvalidOperationException("asset_id and resource_name are required.");
        if (request.columns <= 0 || request.rows <= 0 || request.columns * request.rows != request.frame_count)
            throw new InvalidOperationException("Sprite grid does not match frame_count.");
        if (request.fps <= 0 || request.pixels_per_unit <= 0)
            throw new InvalidOperationException("fps and pixels_per_unit must be positive.");
        if (request.pivot == null || request.pivot.x < 0 || request.pivot.x > 1 || request.pivot.y < 0 || request.pivot.y > 1)
            throw new InvalidOperationException("Pivot must be normalized between zero and one.");
        if (request.resource_name.Any(character => !char.IsLetterOrDigit(character) && character != '_'))
            throw new InvalidOperationException("resource_name contains unsupported characters.");
    }

    private static void ConfigureSpriteSheet(string assetPath, ImportRequest request)
    {
        TextureImporter importer = AssetImporter.GetAtPath(assetPath) as TextureImporter;
        if (importer == null)
            throw new InvalidOperationException($"Texture importer not found: {assetPath}");

        importer.textureType = TextureImporterType.Sprite;
        importer.spriteImportMode = SpriteImportMode.Multiple;
        importer.spritePixelsPerUnit = request.pixels_per_unit;
        importer.alphaIsTransparency = true;
        importer.mipmapEnabled = false;
        importer.filterMode = FilterMode.Bilinear;
        importer.textureCompression = TextureImporterCompression.Uncompressed;
        importer.maxTextureSize = 8192;

        importer.GetSourceTextureWidthAndHeight(out int width, out int height);
        if (width % request.columns != 0 || height % request.rows != 0)
            throw new InvalidOperationException("Texture dimensions are not divisible by the requested grid.");
        int cellWidth = width / request.columns;
        int cellHeight = height / request.rows;
        SpriteMetaData[] sprites = new SpriteMetaData[request.frame_count];
        for (int index = 0; index < request.frame_count; index++)
        {
            int column = index % request.columns;
            int rowFromTop = index / request.columns;
            sprites[index] = new SpriteMetaData
            {
                name = $"{request.resource_name}_{index:00}",
                rect = new Rect(column * cellWidth, height - (rowFromTop + 1) * cellHeight, cellWidth, cellHeight),
                alignment = (int)SpriteAlignment.Custom,
                pivot = new Vector2(request.pivot.x, request.pivot.y),
                border = Vector4.zero
            };
        }

#pragma warning disable 0618
        importer.spritesheet = sprites;
#pragma warning restore 0618
        importer.SaveAndReimport();
    }

    private static string CreateAnimationClip(string spritePath, ImportRequest request)
    {
        Sprite[] sprites = AssetDatabase.LoadAllAssetsAtPath(spritePath)
            .OfType<Sprite>()
            .OrderBy(sprite => sprite.name, StringComparer.Ordinal)
            .ToArray();
        if (sprites.Length != request.frame_count)
            throw new InvalidOperationException($"Imported {sprites.Length} frames, expected {request.frame_count}.");

        string clipPath = $"{AnimationRoot}/{request.resource_name}.anim";
        AnimationClip clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(clipPath);
        if (clip == null)
        {
            clip = new AnimationClip();
            AssetDatabase.CreateAsset(clip, clipPath);
        }
        clip.frameRate = request.fps;
        EditorCurveBinding binding = new EditorCurveBinding
        {
            path = string.Empty,
            type = typeof(SpriteRenderer),
            propertyName = "m_Sprite"
        };
        ObjectReferenceKeyframe[] keys = sprites.Select((sprite, index) => new ObjectReferenceKeyframe
        {
            time = index / request.fps,
            value = sprite
        }).ToArray();
        AnimationUtility.SetObjectReferenceCurve(clip, binding, keys);
        AnimationClipSettings settings = AnimationUtility.GetAnimationClipSettings(clip);
        settings.loopTime = request.loop;
        AnimationUtility.SetAnimationClipSettings(clip, settings);
        EditorUtility.SetDirty(clip);
        return clipPath;
    }

    private static void WriteReports(IEnumerable<ImportReport> reports)
    {
        string reportRoot = Path.Combine(Directory.GetCurrentDirectory(), "Build", "Reports");
        Directory.CreateDirectory(reportRoot);
        foreach (ImportReport report in reports)
        {
            string safeId = string.IsNullOrWhiteSpace(report.asset_id) ? "unknown" : report.asset_id;
            string path = Path.Combine(reportRoot, $"approved-import-{safeId}.json");
            File.WriteAllText(path, JsonUtility.ToJson(report, true));
        }
    }
}
