// Copyright Epic Games, Inc. All Rights Reserved.
#pragma once

#include "Engine/DataAsset.h"
#include "DeadlineJobPreset.generated.h"

// Forward declarations
class UDeadlineJobPreset;
class UScriptCategories;

DECLARE_LOG_CATEGORY_EXTERN(LogDeadlineDataAsset, Log, All);
DECLARE_LOG_CATEGORY_EXTERN(LogDeadlineStruct, Log, All);

/**
 * Deadline Job Info Struct
 */
USTRUCT(BlueprintType)
struct DEADLINESERVICE_API FDeadlineJobPresetStruct
{
	/**
	 * If any of these variable names must change for any reason, be sure to update the string literals in the source as well
	 * such as in DeadlineJobDataAsset.cpp and MoviePipelineDeadline/DeadlineJobPresetCustomization.cpp, et al.
	 */
	GENERATED_BODY()

	/** Specifies the name of the job. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Job Description")
	FString Name = "Untitled";

	/** Specifies a comment for the job. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Job Description", meta = (MultiLine = true))
	FString Comment;

	/**
	 * Specifies the department that the job belongs to.
	 * This is simply a way to group jobs together, and does not affect rendering in any way.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Job Description")
	FString Department;

	/** Specifies the pool that the job is being submitted to. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Job Options")
	FString Pool;

	/**
	 * Specifies the secondary pool that the job can spread to if machines are available.
	 * If not specified, the job will not use a secondary pool.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Job Options")
	FString SecondaryPool;

	/** Specifies the group that the job is being submitted to. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Job Options")
	FString Group;

	/** Specifies the priority of a job with 0 being the lowest and 100 being the highest unless configured otherwise in Repository Options. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Job Options", meta = (ClampMin = 0))
	int32 Priority = 50;

	/** Specifies the time, in seconds, a Worker has to render a task before it times out. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Job Options", meta = (ClampMin = 0))
	int32 TaskTimeoutSeconds = 0;
	
	/**
	 * If true, a Worker will automatically figure out if it has been rendering too long based on some
	 * Repository Configuration settings and the render times of previously completed tasks.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Job Options")
	bool bEnableAutoTimeout = false;
	
	/** Deadline Plugin used to execute the current job. */		
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Plugin")		
	FString Plugin = TEXT("UnrealEngine5");

	/**
	 * Specifies the maximum number of tasks that a Worker can render at a time.
	 * This is useful for script plugins that support multithreading.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Job Options", meta = (ClampMin = 1, ClampMax = 16))
	int32 ConcurrentTasks = 1;
	
	/** If ConcurrentTasks is greater than 1, setting this to true will ensure that a Worker will not dequeue more tasks than it has processors. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Job Options")
	bool bLimitConcurrentTasksToNumberOfCpus = true;

	/** Specifies the maximum number of machines this job can be rendered on at the same time (0 means unlimited). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Job Options", meta = (ClampMin = 0))
	int32 MachineLimit = 0;

	/** If true, the machine names in MachineList will be avoided. todo */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Job Options", DisplayName = "Machine List Is A Deny List")
	bool bMachineListIsADenyList = false;

	/** Job machines to use. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Job Options")
	FString MachineList;

	/** Specifies the limit groups that this job is a member of. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Job Options")
	FString LimitGroups;

	/**
	 * Specifies what jobs must finish before this job will resume (default = blank).
	 * These dependency jobs must be identified using their unique job ID,
	 * which is outputted after the job is submitted, and can be found in the Monitor in the “Job ID” column.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Job Options")
	FString JobDependencies;

	/**
	 * Specifies the frame range of the render job.
	 * See the Frame List Formatting Options in the Job Submission documentation for more information.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Job Options")
	FString Frames = TEXT("0");

	/** Specifies how many frames to render per task. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Job Options", meta = (ClampMin = 1))
	int32 ChunkSize = 1;

	/** Specifies what should happen to a job after it completes. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Job Options", meta = (GetOptions = "GetOnJobCompleteOptions"))
	FString OnJobComplete = "Nothing";

	/** whether the submitted job should be set to 'suspended' status. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Job Options")
	bool bSubmitJobAsSuspended = false;

	/** Specifies the job’s user. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Advanced Job Options")
	FString UserName;

	/** Specifies an optional name to logically group jobs together. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Advanced Job Options")
	FString BatchName;

	/**
	 * Specifies a full path to a python script to execute when the job initially starts rendering.
	 * Note:
	 * This location is expected to already be path mapped on the farm else it will fail.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, AdvancedDisplay, Category = "Advanced Job Options", meta = (FilePathFilter = "Python files (*.py)|*.py"))
	FFilePath PreJobScript;

	/**
	 * Specifies a full path to a python script to execute when the job completes.
	 * Note:
	 * This location is expected to already be path mapped on the farm else it will fail.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, AdvancedDisplay, Category = "Advanced Job Options", meta = (FilePathFilter = "Python files (*.py)|*.py"))
	FFilePath PostJobScript;

	/**
	 * Specifies a full path to a python script to execute before each task starts rendering.
	 * Note:
	 * This location is expected to already be path mapped on the farm else it will fail.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, AdvancedDisplay, Category = "Advanced Job Options", meta = (FilePathFilter = "Python files (*.py)|*.py"))
	FFilePath PreTaskScript;

	/**
	 * Specifies a full path to a python script to execute after each task completes.
	 * Note:
	 * This location is expected to already be path mapped on the farm else it will fail.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, AdvancedDisplay, Category = "Advanced Job Options", meta = (FilePathFilter = "Python files (*.py)|*.py"))
	FFilePath PostTaskScript;

	/** Specifies environment variables to set when the job renders. This is only set in the Deadline environment not the Unreal environment. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, AdvancedDisplay, Category = "Advanced Job Options")
	TMap<FString, FString> EnvironmentKeyValue;

	/** Key Value pair environment variables to set when the job renders. This is only set in the Deadline environment not the Unreal environment. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, AdvancedDisplay, Category = "Advanced Job Options")
	TMap<FString, FString> EnvironmentInfo;

	/** Key-Value pair Job Extra Info keys for storing user data on the job. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, AdvancedDisplay, Category = "Advanced Job Options")
	TMap<FString, FString> ExtraInfoKeyValue;

	/** Replace the Task extra info column names with task extra info value. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, AdvancedDisplay, Category = "Advanced Job Options")
	bool bOverrideTaskExtraInfoNames = false;
	
	/**
	 * Key Value pair Task Extra Info keys for storing deadline info. This is split up into unique
	 * settings as there is a limited amount of settings
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, AdvancedDisplay, Category = "Advanced Job Options")
	TMap<FString, FString> TaskExtraInfoNames;

	/** Extra Deadline Job options. Note: Match the naming convention on Deadline's Manual Job Submission website for the options. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, AdvancedDisplay, Category = "Advanced Job Options")
	TMap<FString, FString> ExtraJobOptions;

	/** Deadline Plugin info key value pair. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Advanced Job Options")
	TMap<FString, FString> PluginInfo;
};


/**
 * Deadline Job Preset
 */
UCLASS(BlueprintType, DontCollapseCategories)
class DEADLINESERVICE_API UDeadlineJobPreset : public UObject
{
	GENERATED_BODY()
public:

	UDeadlineJobPreset();

	/** Job preset struct */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Job Preset")
	FDeadlineJobPresetStruct JobPresetStruct;

	UFUNCTION()
	static TArray<FString> GetOnJobCompleteOptions()
	{
		return {"Nothing","Delete","Archive"};
	}

protected:

	/**
	 * Sets up the PluginInfo struct for the FDeadlineJobPresetStruct.
	 */
	void SetupPluginInfo();

};
