// Copyright Epic Games, Inc. All Rights Reserved.

#include "DeadlineJobPresetCustomization.h"

#include "MoviePipelineDeadlineExecutorJob.h"
#include "MoviePipelineDeadlineSettings.h"

#include "DetailWidgetRow.h"
#include "IDetailChildrenBuilder.h"
#include "IDetailGroup.h"
#include "Widgets/Input/SCheckBox.h"
#include "Widgets/Layout/SBox.h"

class SEyeCheckBox : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS( SEyeCheckBox ){}

	SLATE_END_ARGS()
	
	void Construct(const FArguments& InArgs, const FName& InPropertyPath)
	{		
		ChildSlot
		[
			SNew(SBox)
			.Visibility(EVisibility::Visible)
			.HAlign(HAlign_Right)
			.WidthOverride(28)
			.HeightOverride(20)
			.Padding(4, 0)
			[
				SAssignNew(CheckBoxPtr, SCheckBox)
				.Style(&FAppStyle::Get().GetWidgetStyle<FCheckBoxStyle>("ToggleButtonCheckbox"))
				.Visibility_Lambda([this]()
				{
					return CheckBoxPtr.IsValid() && !CheckBoxPtr->IsChecked() ? EVisibility::Visible : IsHovered() ? EVisibility::Visible : EVisibility::Hidden;
				})
				.CheckedImage(FAppStyle::Get().GetBrush("Icons.Visible"))
				.CheckedHoveredImage(FAppStyle::Get().GetBrush("Icons.Visible"))
				.CheckedPressedImage(FAppStyle::Get().GetBrush("Icons.Visible"))
				.UncheckedImage(FAppStyle::Get().GetBrush("Icons.Hidden"))
				.UncheckedHoveredImage(FAppStyle::Get().GetBrush("Icons.Hidden"))
				.UncheckedPressedImage(FAppStyle::Get().GetBrush("Icons.Hidden"))
				.ToolTipText(NSLOCTEXT("FDeadlineJobPresetLibraryCustomization", "VisibleInMoveRenderQueueToolTip", "If true this property will be visible for overriding from Movie Render Queue."))
				.OnCheckStateChanged_Lambda([InPropertyPath](ECheckBoxState CheckType)
				{
					if (UMoviePipelineDeadlineSettings* Settings =
						GetMutableDefault<UMoviePipelineDeadlineSettings>())
					{
						if (CheckType == ECheckBoxState::Unchecked)
						{
							Settings->AddPropertyToHideInMovieRenderQueue(
								InPropertyPath);
						}
						else
						{
							Settings->
								RemovePropertyToHideInMovieRenderQueue(
									InPropertyPath);
						}
					}
				})
				.IsChecked_Lambda([InPropertyPath]()
				{
					return FDeadlineJobPresetCustomization::IsPropertyHiddenInMovieRenderQueue(InPropertyPath)
								? ECheckBoxState::Unchecked
								: ECheckBoxState::Checked;
				})
			]
		];
	}

	TSharedPtr<SCheckBox> CheckBoxPtr;
};

TSharedRef<IPropertyTypeCustomization> FDeadlineJobPresetCustomization::MakeInstance()
{
	return MakeShared<FDeadlineJobPresetCustomization>();
}

void FDeadlineJobPresetCustomization::CustomizeChildren(TSharedRef<IPropertyHandle> StructHandle,
	IDetailChildrenBuilder& ChildBuilder, IPropertyTypeCustomizationUtils& CustomizationUtils)
{
	TArray<UObject*> OuterObjects;
	StructHandle->GetOuterObjects(OuterObjects);

	if (OuterObjects.Num() == 0)
	{
		return;
	}

	const TWeakObjectPtr<UObject> OuterObject = OuterObjects[0];
	if (!OuterObject.IsValid())
	{
		return;
	}
	
	UMoviePipelineDeadlineExecutorJob* OuterJob = Cast<UMoviePipelineDeadlineExecutorJob>(OuterObject);

	TMap<FName, IDetailGroup*> CreatedCategories;

	const FName StructName(StructHandle->GetProperty()->GetFName());

	if (OuterJob)
	{
		IDetailGroup& BaseCategoryGroup = ChildBuilder.AddGroup(StructName, StructHandle->GetPropertyDisplayName());
		CreatedCategories.Add(StructName, &BaseCategoryGroup);
	}
	
	// For each map member and each struct member in the map member value
	uint32 NumChildren;
	StructHandle->GetNumChildren(NumChildren);
	
	// For each struct member
	for (uint32 ChildIndex = 0; ChildIndex < NumChildren; ++ChildIndex)
	{
		const TSharedRef<IPropertyHandle> ChildHandle = StructHandle->GetChildHandle(ChildIndex).ToSharedRef();

		// Skip properties that are hidden so we don't end up creating empty categories in the job details
		if (OuterJob && IsPropertyHiddenInMovieRenderQueue(*ChildHandle->GetProperty()->GetPathName()))
		{
			continue;
		}
		
		IDetailGroup* GroupToUse = nullptr;
		if (const FString* PropertyCategoryString = ChildHandle->GetProperty()->FindMetaData(TEXT("Category")))
		{
			FName PropertyCategoryName(*PropertyCategoryString);

			if (IDetailGroup** FoundCategory = CreatedCategories.Find(PropertyCategoryName))
			{
				GroupToUse = *FoundCategory;
			}
			else
			{
				if (OuterJob)
				{
					IDetailGroup& NewGroup = CreatedCategories.FindChecked(StructName)->AddGroup(PropertyCategoryName, FText::FromName(PropertyCategoryName), true);
					GroupToUse = CreatedCategories.Add(PropertyCategoryName, &NewGroup);
				}
				else
				{
					IDetailGroup& NewGroup = ChildBuilder.AddGroup(PropertyCategoryName, FText::FromName(PropertyCategoryName));
					NewGroup.ToggleExpansion(true);
					GroupToUse = CreatedCategories.Add(PropertyCategoryName, &NewGroup);
				}
			}
		}
		
		IDetailPropertyRow& PropertyRow = GroupToUse->AddPropertyRow(ChildHandle);

		if (OuterJob)
		{
			CustomizeStructChildrenInMovieRenderQueue(PropertyRow, OuterJob);
		}
		else
		{
			CustomizeStructChildrenInAssetDetails(PropertyRow);
		}
	}

	// Force expansion of all categories
	for (const TTuple<FName, IDetailGroup*>& Pair : CreatedCategories)
	{
		if (Pair.Value)
		{
			Pair.Value->ToggleExpansion(true);
		}
	}
}

void FDeadlineJobPresetCustomization::CustomizeStructChildrenInAssetDetails(IDetailPropertyRow& PropertyRow) const
{
	TSharedPtr<SWidget> NameWidget;
	TSharedPtr<SWidget> ValueWidget;
	FDetailWidgetRow Row;
	PropertyRow.GetDefaultWidgets(NameWidget, ValueWidget, Row);

	PropertyRow.CustomWidget(true)
	.NameContent()
	.MinDesiredWidth(Row.NameWidget.MinWidth)
	.MaxDesiredWidth(Row.NameWidget.MaxWidth)
	.HAlign(HAlign_Fill)
	[
		NameWidget.ToSharedRef()
	]
	.ValueContent()
	.MinDesiredWidth(Row.ValueWidget.MinWidth)
	.MaxDesiredWidth(Row.ValueWidget.MaxWidth)
	.VAlign(VAlign_Center)
	[
		ValueWidget.ToSharedRef()
	]
	.ExtensionContent()
	[
		SNew(SEyeCheckBox, *PropertyRow.GetPropertyHandle()->GetProperty()->GetPathName())
	];
}

void FDeadlineJobPresetCustomization::CustomizeStructChildrenInMovieRenderQueue(
	IDetailPropertyRow& PropertyRow, UMoviePipelineDeadlineExecutorJob* Job) const
{	
	TSharedPtr<SWidget> NameWidget;
	TSharedPtr<SWidget> ValueWidget;
	FDetailWidgetRow Row;
	PropertyRow.GetDefaultWidgets(NameWidget, ValueWidget, Row);
	
	const FName PropertyPath = *PropertyRow.GetPropertyHandle()->GetProperty()->GetPathName();

	ValueWidget->SetEnabled(TAttribute<bool>::CreateLambda([Job, PropertyPath]()
			{
				if (!Job)
				{
					// Return true so by default all properties are enabled for overrides 
					return true;
				}
				
				return Job->IsPropertyRowEnabledInMovieRenderJob(PropertyPath); 
			}));
	
	PropertyRow
	.OverrideResetToDefault(
		FResetToDefaultOverride::Create(
			FIsResetToDefaultVisible::CreateStatic( &FDeadlineJobPresetCustomization::IsResetToDefaultVisibleOverride, Job),
			FResetToDefaultHandler::CreateStatic(&FDeadlineJobPresetCustomization::ResetToDefaultOverride, Job)))
	.CustomWidget(true)
	.NameContent()
	.MinDesiredWidth(Row.NameWidget.MinWidth)
	.MaxDesiredWidth(Row.NameWidget.MaxWidth)
	.HAlign(HAlign_Fill)
	[
		SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.Padding(4, 0)
		[
			SNew(SCheckBox)
			.IsChecked_Lambda([Job, PropertyPath]()
			{
				if (!Job)
				{
					// Return Checked so by default all properties are enabled for overrides 
					return ECheckBoxState::Checked;
				}
				
				return Job->IsPropertyRowEnabledInMovieRenderJob(PropertyPath) ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; 
			})
			.OnCheckStateChanged_Lambda([Job, PropertyPath](const ECheckBoxState NewState)
			{
				if (!Job)
				{
					return;
				}
				
				return Job->SetPropertyRowEnabledInMovieRenderJob(
					PropertyPath, NewState == ECheckBoxState::Checked ? true : false); 
			})
		]
		+ SHorizontalBox::Slot()
		[
			NameWidget.ToSharedRef()
		]
	]
	.ValueContent()
	.MinDesiredWidth(Row.ValueWidget.MinWidth)
	.MaxDesiredWidth(Row.ValueWidget.MaxWidth)
	.VAlign(VAlign_Center)
	[
		ValueWidget.ToSharedRef()
	];
}

bool FDeadlineJobPresetCustomization::IsPropertyHiddenInMovieRenderQueue(const FName& InPropertyPath)
{
	if (const UMoviePipelineDeadlineSettings* Settings = GetDefault<UMoviePipelineDeadlineSettings>())
	{
		return Settings->GetIsPropertyHiddenInMovieRenderQueue(InPropertyPath);
	}
	return false;
}

bool FDeadlineJobPresetCustomization::IsPropertyRowEnabledInMovieRenderJob(const FName& InPropertyPath,
	UMoviePipelineDeadlineExecutorJob* Job)
{
	return Job && Job->IsPropertyRowEnabledInMovieRenderJob(InPropertyPath); 
}

bool GetPresetValueAsString(const FProperty* PropertyPtr, UMoviePipelineDeadlineExecutorJob* Job, FString& OutFormattedValue)
{
	if (!PropertyPtr || !Job)
	{
		return false;
	}

	UDeadlineJobPreset* SelectedJobPreset = Job->JobPreset;
	if (!SelectedJobPreset)
	{
		return false;
	}

	const void* ValuePtr = PropertyPtr->ContainerPtrToValuePtr<void>(&SelectedJobPreset->JobPresetStruct);
	PropertyPtr->ExportText_Direct(OutFormattedValue, ValuePtr, ValuePtr, nullptr, PPF_None);
	return true;
}

bool FDeadlineJobPresetCustomization::IsResetToDefaultVisibleOverride(
	TSharedPtr<IPropertyHandle> PropertyHandle, UMoviePipelineDeadlineExecutorJob* Job)
{
	if (!PropertyHandle || !Job)
	{
		return true;
	}
	
	if (FString DefaultValueAsString; GetPresetValueAsString(PropertyHandle->GetProperty(), Job, DefaultValueAsString))
	{
		FString CurrentValueAsString;
		PropertyHandle->GetValueAsFormattedString(CurrentValueAsString);

		return CurrentValueAsString != DefaultValueAsString; 
	}

	// If this fails, just show it by default
	return true;
}

void FDeadlineJobPresetCustomization::ResetToDefaultOverride(
	TSharedPtr<IPropertyHandle> PropertyHandle, UMoviePipelineDeadlineExecutorJob* Job)
{
	if (!PropertyHandle || !Job)
	{
		return;
	}
	
	if (FString DefaultValueAsString; GetPresetValueAsString(PropertyHandle->GetProperty(), Job, DefaultValueAsString))
	{
		PropertyHandle->SetValueFromFormattedString(DefaultValueAsString);
	}
}
