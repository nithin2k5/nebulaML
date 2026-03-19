"use client";

import { useState, useEffect } from "react";
import { useAuth } from "@/context/AuthContext";
import { API_ENDPOINTS } from "@/lib/config";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { RefreshCw, AlertTriangle, CheckCircle, Info, TrendingUp, BarChart2, Target, Settings } from "lucide-react";

export default function DatasetAnalysisTab({ datasetId }) {
  const { token } = useAuth();
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (datasetId) {
      fetchAnalysis();
    }
  }, [datasetId]);

  const fetchAnalysis = async () => {
    if (!datasetId) return;

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(API_ENDPOINTS.DATASETS.ANALYZE(datasetId), {
        headers: { "Authorization": `Bearer ${token}` }
      });
      const data = await response.json();

      if (data.success) {
        setAnalysis(data.analysis);
      } else {
        setError("Failed to analyze dataset");
      }
    } catch (err) {
      console.error("Analysis error:", err);
      setError("Error fetching analysis. Make sure backend is running.");
    } finally {
      setLoading(false);
    }
  };

  const getQualityColor = (score) => {
    if (score >= 80) return "text-green-500";
    if (score >= 60) return "text-yellow-500";
    return "text-red-500";
  };

  const getQualityBadge = (score) => {
    if (score >= 80) return "bg-green-500/20 text-green-500 border-green-500/30";
    if (score >= 60) return "bg-yellow-500/20 text-yellow-500 border-yellow-500/30";
    return "bg-red-500/20 text-red-500 border-red-500/30";
  };

  if (!datasetId) {
    return (
      <div className="flex items-center justify-center py-12 text-muted-foreground">
        <p>Select a dataset to view analysis</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <RefreshCw className="text-4xl mb-4 animate-spin text-primary" />
        <p className="text-sm text-muted-foreground">Analyzing dataset...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <AlertTriangle className="text-4xl mb-4 text-destructive" />
        <p className="text-sm text-destructive mb-4">{error}</p>
        <Button onClick={fetchAnalysis} variant="outline">
          <RefreshCw className="mr-2" />
          Retry
        </Button>
      </div>
    );
  }

  if (!analysis) {
    return (
      <div className="flex items-center justify-center py-12 text-muted-foreground">
        <p>No analysis data available</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold text-primary">Dataset Analysis</h2>
          <p className="text-muted-foreground">{analysis.dataset_name}</p>
        </div>
        <Button onClick={fetchAnalysis} variant="outline" disabled={loading}>
          <RefreshCw className={`mr-2 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {/* Overall Quality Score */}
      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Target className="text-primary" />
            Overall Quality Score
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-2xl font-bold">Score</span>
              <span className={`text-4xl font-bold ${getQualityColor(analysis.overall_quality_score)}`}>
                {analysis.overall_quality_score.toFixed(1)}
              </span>
            </div>
            <Progress value={analysis.overall_quality_score} className="h-3" />
            <Badge className={getQualityBadge(analysis.overall_quality_score)}>
              {analysis.overall_quality_score >= 80 ? "Excellent" :
                analysis.overall_quality_score >= 60 ? "Good" : "Needs Improvement"}
            </Badge>
          </div>
        </CardContent>
      </Card>

      {/* Warnings & Recommendations */}
      {(analysis.warnings?.length > 0 || analysis.recommendations?.length > 0) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {analysis.warnings?.length > 0 && (
            <Card className="bg-yellow-500/10 border-yellow-500/30">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-yellow-500">
                  <AlertTriangle />
                  Warnings ({analysis.warnings.length})
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2">
                  {analysis.warnings.map((warning, idx) => (
                    <li key={idx} className="text-sm flex items-start gap-2">
                      <AlertTriangle className="text-yellow-500 mt-0.5 flex-shrink-0" />
                      <span>{warning}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}

          {analysis.recommendations?.length > 0 && (
            <Card className="bg-blue-500/10 border-blue-500/30">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-blue-500">
                  <Info />
                  Recommendations ({analysis.recommendations.length})
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2">
                  {analysis.recommendations.map((rec, idx) => (
                    <li key={idx} className="text-sm flex items-start gap-2">
                      <Info className="text-blue-500 mt-0.5 flex-shrink-0" />
                      <span>{rec}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* Basic Statistics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="bg-card border-border">
          <CardHeader className="pb-2">
            <CardDescription>Total Images</CardDescription>
            <CardTitle className="text-2xl">{analysis.total_images}</CardTitle>
          </CardHeader>
        </Card>
        <Card className="bg-card border-border">
          <CardHeader className="pb-2">
            <CardDescription>Annotated Images</CardDescription>
            <CardTitle className="text-2xl">{analysis.annotated_images}</CardTitle>
          </CardHeader>
        </Card>
        <Card className="bg-card border-border">
          <CardHeader className="pb-2">
            <CardDescription>Total Annotations</CardDescription>
            <CardTitle className="text-2xl">{analysis.total_annotations}</CardTitle>
          </CardHeader>
        </Card>
        <Card className="bg-card border-border">
          <CardHeader className="pb-2">
            <CardDescription>Classes</CardDescription>
            <CardTitle className="text-2xl">{analysis.classes?.length || 0}</CardTitle>
          </CardHeader>
        </Card>
      </div>

      {/* Quality Metrics */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="bg-card border-border">
          <CardHeader>
            <CardTitle className="text-lg">Class Balance</CardTitle>
            <CardDescription>Distribution across classes</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span>Score</span>
                <span className="font-bold">{(analysis.class_balance_score * 100).toFixed(1)}%</span>
              </div>
              <Progress value={analysis.class_balance_score * 100} className="h-2" />
            </div>
          </CardContent>
        </Card>

        <Card className="bg-card border-border">
          <CardHeader>
            <CardTitle className="text-lg">Label Accuracy</CardTitle>
            <CardDescription>Correctness of annotations</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span>Score</span>
                <span className="font-bold">{(analysis.label_accuracy_score * 100).toFixed(1)}%</span>
              </div>
              <Progress value={analysis.label_accuracy_score * 100} className="h-2" />
            </div>
          </CardContent>
        </Card>

        <Card className="bg-card border-border">
          <CardHeader>
            <CardTitle className="text-lg">IoU Consistency</CardTitle>
            <CardDescription>Bounding box quality</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span>Score</span>
                <span className="font-bold">{(analysis.iou_consistency_score * 100).toFixed(1)}%</span>
              </div>
              <Progress value={analysis.iou_consistency_score * 100} className="h-2" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Class Distribution */}
      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <BarChart2 className="text-primary" />
            Class Distribution
          </CardTitle>
          <CardDescription>Number of annotations per class</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {Object.entries(analysis.class_frequency || {}).map(([className, count]) => {
              const maxCount = Math.max(...Object.values(analysis.class_frequency || {}));
              const percentage = maxCount > 0 ? (count / maxCount) * 100 : 0;
              return (
                <div key={className} className="space-y-1">
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-medium">{className}</span>
                    <span className="text-muted-foreground">{count} annotations</span>
                  </div>
                  <Progress value={percentage} className="h-2" />
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Object Size Distribution */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="bg-card border-border">
          <CardHeader>
            <CardTitle className="text-lg">Object Size Distribution</CardTitle>
            <CardDescription>Relative to image size</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {Object.entries(analysis.object_size_distribution || {}).map(([size, count]) => {
                const total = Object.values(analysis.object_size_distribution || {}).reduce((a, b) => a + b, 0);
                const percentage = total > 0 ? (count / total) * 100 : 0;
                return (
                  <div key={size} className="space-y-1">
                    <div className="flex items-center justify-between text-sm">
                      <span className="font-medium capitalize">{size}</span>
                      <span className="text-muted-foreground">{count} ({percentage.toFixed(1)}%)</span>
                    </div>
                    <Progress value={percentage} className="h-2" />
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>

        <Card className="bg-card border-border">
          <CardHeader>
            <CardTitle className="text-lg">Aspect Ratio Distribution</CardTitle>
            <CardDescription>Width to height ratio</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {Object.entries(analysis.aspect_ratio_distribution || {}).map(([ratio, count]) => {
                const total = Object.values(analysis.aspect_ratio_distribution || {}).reduce((a, b) => a + b, 0);
                const percentage = total > 0 ? (count / total) * 100 : 0;
                return (
                  <div key={ratio} className="space-y-1">
                    <div className="flex items-center justify-between text-sm">
                      <span className="font-medium capitalize">{ratio}</span>
                      <span className="text-muted-foreground">{count} ({percentage.toFixed(1)}%)</span>
                    </div>
                    <Progress value={percentage} className="h-2" />
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Training Recommendations */}
      <Card className="bg-card border-border">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Settings className="text-primary" />
            Training Recommendations
          </CardTitle>
          <CardDescription>Suggested configuration based on dataset analysis</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
            <div className="space-y-1">
              <p className="text-sm text-muted-foreground">Image Size</p>
              <p className="text-2xl font-bold">{analysis.recommended_image_size}px</p>
            </div>
            <div className="space-y-1">
              <p className="text-sm text-muted-foreground">Batch Size</p>
              <p className="text-2xl font-bold">{analysis.recommended_batch_size}</p>
            </div>
            <div className="space-y-1">
              <p className="text-sm text-muted-foreground">Epochs</p>
              <p className="text-2xl font-bold">{analysis.recommended_epochs}</p>
            </div>
          </div>

          {analysis.augmentation_recommendations && (
            <div className="mt-4 pt-4 border-t border-border">
              <p className="text-sm font-medium mb-2">Augmentation Settings</p>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm">
                {Object.entries(analysis.augmentation_recommendations).map(([key, value]) => (
                  <div key={key} className="flex items-center justify-between p-2 bg-background rounded">
                    <span className="text-muted-foreground capitalize">{key.replace('_', ' ')}</span>
                    <span className="font-medium">
                      {typeof value === 'boolean' ? (value ? 'On' : 'Off') : value}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Issues */}
      {(analysis.corrupt_images?.length > 0 ||
        analysis.duplicate_images?.length > 0 ||
        analysis.label_mismatches?.length > 0 ||
        analysis.invalid_boxes?.length > 0 ||
        analysis.empty_annotations?.length > 0 ||
        analysis.boxes_out_of_bounds?.length > 0 ||
        analysis.invalid_class_ids?.length > 0) && (
          <Card className="bg-card border-border">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-destructive">
                <AlertTriangle />
                Issues Detected
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {analysis.corrupt_images?.length > 0 && (
                  <div>
                    <p className="text-sm font-medium mb-2">
                      Corrupt Images ({analysis.corrupt_images.length})
                    </p>
                    <div className="text-xs text-muted-foreground space-y-1 max-h-32 overflow-y-auto">
                      {analysis.corrupt_images.slice(0, 10).map((img, idx) => (
                        <div key={idx}>{img}</div>
                      ))}
                      {analysis.corrupt_images.length > 10 && (
                        <div>... and {analysis.corrupt_images.length - 10} more</div>
                      )}
                    </div>
                  </div>
                )}

                {analysis.duplicate_images?.length > 0 && (
                  <div>
                    <p className="text-sm font-medium mb-2">
                      Duplicate Images ({analysis.duplicate_images.length})
                    </p>
                    <div className="text-xs text-muted-foreground space-y-1 max-h-32 overflow-y-auto">
                      {analysis.duplicate_images.slice(0, 10).map((img, idx) => (
                        <div key={idx}>{img}</div>
                      ))}
                      {analysis.duplicate_images.length > 10 && (
                        <div>... and {analysis.duplicate_images.length - 10} more</div>
                      )}
                    </div>
                  </div>
                )}

                {analysis.label_mismatches?.length > 0 && (
                  <div>
                    <p className="text-sm font-medium mb-2">
                      Label Mismatches ({analysis.label_mismatches.length})
                    </p>
                    <div className="text-xs text-muted-foreground space-y-1 max-h-32 overflow-y-auto">
                      {analysis.label_mismatches.slice(0, 10).map((img, idx) => (
                        <div key={idx}>{img}</div>
                      ))}
                      {analysis.label_mismatches.length > 10 && (
                        <div>... and {analysis.label_mismatches.length - 10} more</div>
                      )}
                    </div>
                  </div>
                )}

                {analysis.invalid_boxes?.length > 0 && (
                  <div>
                    <p className="text-sm font-medium mb-2">
                      Invalid Boxes ({analysis.invalid_boxes.length})
                    </p>
                    <div className="text-xs text-muted-foreground">
                      Boxes with zero or negative dimensions detected
                    </div>
                  </div>
                )}

                {analysis.empty_annotations?.length > 0 && (
                  <div>
                    <p className="text-sm font-medium mb-2">
                      Empty Annotations ({analysis.empty_annotations.length})
                    </p>
                    <div className="text-xs text-muted-foreground space-y-1 max-h-32 overflow-y-auto">
                      {analysis.empty_annotations.slice(0, 10).map((img, idx) => (
                        <div key={idx}>{img}</div>
                      ))}
                      {analysis.empty_annotations.length > 10 && (
                        <div>... and {analysis.empty_annotations.length - 10} more</div>
                      )}
                    </div>
                  </div>
                )}

                {analysis.boxes_out_of_bounds?.length > 0 && (
                  <div>
                    <p className="text-sm font-medium mb-2 text-red-500">
                      Out of Bounds Boxes ({analysis.boxes_out_of_bounds.length})
                    </p>
                    <div className="text-xs text-muted-foreground space-y-1 max-h-32 overflow-y-auto">
                      {analysis.boxes_out_of_bounds.slice(0, 5).map((issue, idx) => (
                        <div key={idx} className="text-red-400">{issue}</div>
                      ))}
                      {analysis.boxes_out_of_bounds.length > 5 && (
                        <div>... and {analysis.boxes_out_of_bounds.length - 5} more</div>
                      )}
                    </div>
                  </div>
                )}

                {analysis.invalid_class_ids?.length > 0 && (
                  <div>
                    <p className="text-sm font-medium mb-2">
                      Invalid Class IDs ({analysis.invalid_class_ids.length})
                    </p>
                    <div className="text-xs text-muted-foreground space-y-1 max-h-32 overflow-y-auto">
                      {analysis.invalid_class_ids.slice(0, 5).map((issue, idx) => (
                        <div key={idx}>{issue}</div>
                      ))}
                      {analysis.invalid_class_ids.length > 5 && (
                        <div>... and {analysis.invalid_class_ids.length - 5} more</div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        )}

      {/* Split Analysis */}
      {analysis.split_distribution && (
        <Card className="bg-card border-border">
          <CardHeader>
            <CardTitle className="text-lg">Dataset Splits</CardTitle>
            <CardDescription>Train/Val/Test distribution</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {Object.entries(analysis.split_distribution).map(([split, count]) => {
                const total = Object.values(analysis.split_distribution).reduce((a, b) => a + b, 0);
                const percentage = total > 0 ? (count / total) * 100 : 0;
                return (
                  <div key={split} className="space-y-1">
                    <div className="flex items-center justify-between text-sm">
                      <span className="font-medium capitalize">{split === 'none' ? 'Unassigned' : split}</span>
                      <span className="text-muted-foreground">
                        {count} ({percentage.toFixed(1)}%)
                      </span>
                    </div>
                    <Progress value={percentage} className="h-2" />
                  </div>
                );
              })}
            </div>
            {analysis.data_leakage_detected && (
              <div className="mt-4 p-3 bg-yellow-500/10 border border-yellow-500/30 rounded text-sm text-yellow-500">
                <AlertTriangle className="inline mr-2" />
                Data leakage detected - same images appear in multiple splits
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
